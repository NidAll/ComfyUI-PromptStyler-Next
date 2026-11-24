"""Fast LFM3-VL decoding: one CUDA graph per token over fixed caches.

Transformers' generate loop leaves the GPU idle most of the time on this 2B model (Python and
per-kernel launch overhead). This engine reuses the loaded Comfy INT8 layers, runs the prefill
once in eager mode, then replays a captured decode step: full-attention layers write a fixed KV
cache, sliding-window layers a 256-slot ring (attention is order free, RoPE is applied before
the write) and short-conv layers keep their last ``kernel - 1`` inputs. Stop checks read the
generated tokens every few steps, so the host rarely waits on the device.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import comfy.model_management as mm
import comfy.ops
import torch
import torch.nn.functional as F

CHECK_EVERY = 8


def _rotate_half(x):
    half = x.shape[-1] // 2
    return torch.cat((-x[..., half:], x[..., :half]), dim=-1)


def _rope(x, cos, sin):
    # float32 like the reference implementation; cos/sin are [seq, dim] broadcast over heads
    xf = x.float()
    return (xf * cos + _rotate_half(xf) * sin).to(x.dtype)


@dataclass
class Sampling:
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 0
    min_p: float = 0.0
    repetition_penalty: float = 1.0
    seed: int = 0

    @property
    def greedy(self):
        return self.temperature <= 0.0


class Lfm3Engine:
    """Owns the caches and the captured graph for one LFM3-VL network (``owner.model.network``)."""

    def __init__(self, network, device):
        self.network = network
        self.lm = network.model.language_model
        self.config = self.lm.config
        self.device = device
        self.dtype = torch.bfloat16
        self.layer_types = list(self.config.layer_types)
        self.window = int(self.config.sliding_window)
        self.kernel = int(self.config.conv_L_cache)
        self.kv_heads = int(self.config.num_key_value_heads)
        self.heads = int(self.config.num_attention_heads)
        self.head_dim = int(self.config.head_dim)
        self.capacity = 0
        self.graph = None
        self.tables = {}
        self.weights = None

    def _weights(self):
        # a captured graph reads weights by address: an offload/reload moves them and needs a recapture
        return tuple(p.data_ptr() for p in self.network.parameters())

    # -- setup ---------------------------------------------------------------------------------
    def _tables(self, capacity):
        positions = torch.arange(capacity, device=self.device)
        tables = {}
        for kind in self.lm.rotary_emb.layer_types:
            cos, sin = self.lm.rotary_emb(torch.empty((), device=self.device, dtype=self.dtype), positions[None], kind)
            tables[kind] = (cos[0].float(), sin[0].float())
        return tables

    def _allocate(self, capacity):
        # round up so short follow-up prompts reuse the captured graph
        capacity = max(1024, -(-capacity // 512) * 512)
        if capacity <= self.capacity:
            return
        self.graph = None
        self.capacity = capacity
        self.tables = self._tables(capacity)
        d, t = self.device, self.dtype
        hidden = self.config.hidden_size
        self.caches = []
        for kind in self.layer_types:
            if kind == "conv":
                self.caches.append(torch.zeros((1, hidden, self.kernel - 1), device=d, dtype=t))
            else:
                size = capacity if kind == "full_attention" else self.window
                k = torch.zeros((1, self.kv_heads, size, self.head_dim), device=d, dtype=t)
                self.caches.append((k, torch.zeros_like(k)))
        self.token = torch.zeros((1, 1), device=d, dtype=torch.long)
        self.position = torch.zeros((1,), device=d, dtype=torch.long)
        self.logits = torch.zeros((1, self.config.vocab_size), device=d, dtype=torch.float32)
        self.slots = torch.arange(capacity, device=d)

    # -- model pieces ----------------------------------------------------------------------------
    def _conv(self, layer, index, h, decode):
        conv = layer.conv
        bcx = conv.in_proj(h).transpose(-1, -2)
        b, c, x = bcx.chunk(3, dim=-2)
        bx = b * x
        state = self.caches[index]
        weight = conv.conv.weight
        if decode:
            window = torch.cat((state, bx), dim=-1)
            out = (window.float() * weight[:, 0, :].float()).sum(-1, keepdim=True).to(bx.dtype)
            state.copy_(window[:, :, 1:])
        else:
            n = bx.shape[-1]
            out = F.conv1d(bx.to(weight.dtype), weight, conv.conv.bias, padding=self.kernel - 1, groups=bx.shape[1])[..., :n]
            tail = bx[:, :, -(self.kernel - 1):]
            state.zero_()
            state[:, :, state.shape[-1] - tail.shape[-1]:].copy_(tail)
        if conv.conv.bias is not None and decode:
            out = out + conv.conv.bias[None, :, None]
        y = (c * out).transpose(-1, -2).contiguous()
        return conv.out_proj(y)

    def _attention(self, layer, index, h, cos, sin, decode, start=0):
        attn = layer.self_attn
        kind = self.layer_types[index]
        n = h.shape[1]
        qkv = attn.qkv_proj(h) if hasattr(attn, "qkv_proj") else None
        if qkv is not None:
            q, k, v = qkv.split(attn.qkv_split_sizes, dim=-1)
        else:
            q, k, v = attn.q_proj(h), attn.k_proj(h), attn.v_proj(h)
        q = attn.q_norm(q.view(1, n, self.heads, self.head_dim)).transpose(1, 2)
        k = attn.k_norm(k.view(1, n, self.kv_heads, self.head_dim)).transpose(1, 2)
        v = v.view(1, n, self.kv_heads, self.head_dim).transpose(1, 2)
        q, k = _rope(q, cos, sin), _rope(k, cos, sin)
        key, value = self.caches[index]
        if decode:
            if kind == "full_attention":
                key.index_copy_(2, self.position, k)
                value.index_copy_(2, self.position, v)
                mask = (self.slots[: key.shape[2]] <= self.position)[None, None, None]
            else:
                slot = torch.remainder(self.position, self.window)
                key.index_copy_(2, slot, k)
                value.index_copy_(2, slot, v)
                mask = (self.slots[: self.window] <= self.position)[None, None, None]
            out = F.scaled_dot_product_attention(q, key, value, attn_mask=mask, scale=attn.scaling, enable_gqa=True)
        else:
            positions = torch.arange(start, start + n, device=h.device)
            causal = positions[None, :] <= positions[:, None]
            if kind != "full_attention":
                causal &= positions[:, None] - positions[None, :] < self.window
            out = F.scaled_dot_product_attention(q, k, v, attn_mask=causal[None, None], scale=attn.scaling, enable_gqa=True)
            if kind == "full_attention":
                key[:, :, start:start + n].copy_(k)
                value[:, :, start:start + n].copy_(v)
            else:
                keep = min(n, self.window)
                slots = torch.remainder(positions[-keep:], self.window)
                key.index_copy_(2, slots, k[:, :, -keep:])
                value.index_copy_(2, slots, v[:, :, -keep:])
        gate = torch.sigmoid(attn.gate_proj(h)).unsqueeze(-1)
        out = (out.transpose(1, 2) * gate).reshape(1, n, -1)
        return attn.o_proj(out)

    def _forward(self, x, cos_sin, decode, start=0):
        for index, layer in enumerate(self.lm.layers):
            residual = x
            h = layer.operator_norm(x)
            if layer.is_attention_layer:
                cos, sin = cos_sin[self.layer_types[index]]
                h = self._attention(layer, index, h, cos, sin, decode, start)
            else:
                h = self._conv(layer, index, h, decode)
            if layer.use_sandwich_norm:
                h = layer.post_operator_norm(h)
            x = h + residual
            ffn = layer.feed_forward(layer.ffn_norm(x))
            if layer.use_sandwich_norm:
                ffn = layer.post_ffn_norm(ffn)
            x = x + ffn
        return self.network.lm_head(self.lm.embedding_norm(x[:, -1:]))[:, -1].float()

    def _decode_step(self):
        x = self.lm.embed_tokens(self.token).to(self.dtype)
        cos_sin = {kind: (cos.index_select(0, self.position), sin.index_select(0, self.position))
                   for kind, (cos, sin) in self.tables.items()}
        self.logits.copy_(self._forward(x, cos_sin, decode=True))

    def _capture(self):
        stream = torch.cuda.Stream(self.device)
        stream.wait_stream(torch.cuda.current_stream(self.device))
        saved = [c.clone() if torch.is_tensor(c) else (c[0].clone(), c[1].clone()) for c in self.caches]
        with torch.cuda.stream(stream):
            for _ in range(2):
                self._decode_step()
        torch.cuda.current_stream(self.device).wait_stream(stream)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph, stream=stream):
            self._decode_step()
        # warmup and capture ran the step for real: put the prefill state back
        for cache, copy in zip(self.caches, saved, strict=True):
            if torch.is_tensor(cache):
                cache.copy_(copy)
            else:
                cache[0].copy_(copy[0]); cache[1].copy_(copy[1])
        self.graph = graph
        self.weights = self._weights()

    # -- public ----------------------------------------------------------------------------------
    @torch.no_grad()
    def embeds(self, inputs):
        """Text embeddings with image features scattered in, as the VL model's forward builds them."""
        vl = self.network.model
        input_ids = inputs["input_ids"]
        embeds = vl.get_input_embeddings()(input_ids).to(self.dtype)
        if inputs.get("pixel_values") is not None:
            extra = {k: v for k, v in inputs.items() if k not in ("input_ids", "attention_mask", "pixel_values")}
            features = vl.get_image_features(inputs["pixel_values"], return_dict=True, **extra)
            features = torch.cat(features.pooler_output, dim=0).to(embeds.device, embeds.dtype)
            mask, _ = vl.get_placeholder_mask(input_ids, inputs_embeds=embeds, image_features=features)
            embeds = embeds.masked_scatter(mask, features)
        return embeds

    @torch.no_grad()
    def generate(self, inputs, max_new_tokens, stop_tokens, sampling: Sampling | None = None, use_graph=True,
                 stop_fn=None, on_tokens=None):
        """Decode up to ``max_new_tokens``. ``stop_fn(tokens)`` may return a cut length (tokens kept) or None.

        Returns ``(tokens, stopped, info)``; ``stopped`` is False when the budget ran out first.
        """
        sampling = sampling or Sampling()
        stop_tokens = set(stop_tokens)
        started = time.perf_counter()
        with comfy.ops.use_quantized_matmul(self.network, self.device):
            embeds = self.embeds(inputs)
            n = embeds.shape[1]
            self._allocate(n + max_new_tokens + 1)
            for cache in self.caches:
                if torch.is_tensor(cache):
                    cache.zero_()
                else:
                    cache[0].zero_(); cache[1].zero_()
            cos_sin = {kind: (cos[:n], sin[:n]) for kind, (cos, sin) in self.tables.items()}
            logits = self._forward(embeds, cos_sin, decode=False)
            generator = torch.Generator(device=self.device).manual_seed(int(sampling.seed) & 0xFFFFFFFFFFFFFFFF)
            seen = torch.zeros((self.config.vocab_size,), device=self.device, dtype=torch.bool)
            seen[inputs["input_ids"][0].to(self.device)] = True
            out = torch.empty((max_new_tokens,), device=self.device, dtype=torch.long)
            next_token = self._pick(logits, sampling, seen, generator)
            self.position.fill_(n)
            if use_graph and (self.graph is None or self.weights != self._weights()):
                self.token.copy_(next_token.view(1, 1))
                self._capture()
            torch.cuda.synchronize(self.device)
            prefilled = time.perf_counter()
            tokens, stopped, checked = [], False, 0
            for step in range(max_new_tokens):
                out[step] = next_token
                seen[next_token] = True
                last = step + 1 == max_new_tokens
                if (step + 1) % CHECK_EVERY == 0 or last:
                    # one host sync per window: scan the new tokens for a stop
                    mm.throw_exception_if_processing_interrupted()
                    tokens.extend(out[checked:step + 1].tolist())
                    for index in range(checked, step + 1):
                        if tokens[index] in stop_tokens:
                            del tokens[index + 1:]
                            stopped = True
                            break
                    if not stopped and stop_fn is not None:
                        cut = stop_fn(tokens)
                        if cut is not None:
                            del tokens[cut:]
                            stopped = True
                    checked = step + 1
                    if on_tokens is not None:
                        on_tokens(len(tokens))
                    if stopped:
                        break
                if last:
                    break
                self.token.copy_(next_token.view(1, 1))
                if use_graph:
                    self.graph.replay()
                else:
                    self._decode_step()
                self.position.add_(1)
                next_token = self._pick(self.logits, sampling, seen, generator)
        finished = time.perf_counter()
        return tokens, stopped, {
            "input_tokens": n,
            "generated_tokens": len(tokens),
            "prefill_seconds": round(prefilled - started, 3),
            "decode_seconds": round(finished - prefilled, 3),
            "tokens_per_second": round(len(tokens) / max(finished - prefilled, 1e-6), 1),
            "engine": "graph" if use_graph else "eager",
        }

    def _pick(self, logits, sampling, seen, generator):
        logits = logits.float().view(-1)
        if sampling.repetition_penalty != 1.0:
            penalty = torch.where(logits > 0, 1.0 / sampling.repetition_penalty, sampling.repetition_penalty)
            logits = torch.where(seen, logits * penalty, logits)
        if sampling.greedy:
            return logits.argmax()
        logits = logits / sampling.temperature
        if sampling.top_k > 0:
            values, indices = torch.topk(logits, min(sampling.top_k, logits.numel()))
        else:
            values, indices = torch.sort(logits, descending=True)
        probs = torch.softmax(values, dim=-1)
        if sampling.min_p > 0.0:
            probs = torch.where(probs < sampling.min_p * probs[0], 0.0, probs)
        if sampling.top_p < 1.0:
            cumulative = probs.cumsum(-1)
            probs = torch.where(cumulative - probs > sampling.top_p, 0.0, probs)
        choice = torch.multinomial(probs / probs.sum(), 1, generator=generator)
        return indices[choice[0]]


def engine_for(handle):
    """One engine per loader handle (the loader node caches the handle, not the model)."""
    owner = handle.owner
    engine = getattr(handle, "engine", None)
    if engine is None or engine.device != owner.load_device or engine.network is not owner.model.network:
        engine = Lfm3Engine(owner.model.network, owner.load_device)
        handle.engine = engine
    return engine
