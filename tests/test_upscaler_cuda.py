"""Run explicitly on the host CUDA context with ComfyUI on PYTHONPATH."""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

import pytest

if os.environ.get("PSNEXT_RUN_CUDA_TESTS") != "1":
    pytest.skip("Set PSNEXT_RUN_CUDA_TESTS=1 in the CUDA host environment", allow_module_level=True)

import comfy.ops
import torch
from transformers.cache_utils import DynamicCache
from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig
from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5GatedDeltaNet

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "psnext_cuda_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
from psnext_cuda_test.comfyui.upscaler.native import NativeDeltaNet, NativeRMSNorm, merge_int8  # noqa: E402


@unittest.skipUnless(torch.cuda.is_available(), "requires CUDA")
class NativeDecodeTests(unittest.TestCase):
    def test_int8_projection_fusion_preserves_bytes_and_output(self):
        ops = comfy.ops.mixed_precision_ops(compute_dtype=torch.bfloat16)
        metadata = torch.tensor(
            list(
                json.dumps({"format": "int8_tensorwise", "convrot": True, "convrot_groupsize": 256}).encode()
            ),
            dtype=torch.uint8,
        )
        layers = []
        for rows in (256, 512):
            layer = ops.Linear(256, rows, bias=False, device="cpu")
            layer.load_state_dict(
                {
                    "weight": torch.randint(-127, 128, (rows, 256), dtype=torch.int8),
                    "weight_scale": torch.full((rows, 1), 0.001),
                    "comfy_quant": metadata,
                },
                strict=True,
            )
            layers.append(layer)
        merged = merge_int8(layers)
        torch.testing.assert_close(
            merged.state_dict()["weight"],
            torch.cat([layer.state_dict()["weight"] for layer in layers]),
            atol=0,
            rtol=0,
        )
        merged.to("cuda")
        for layer in layers:
            layer.to("cuda")
        with torch.inference_mode():
            for length in (1, 16):
                x = torch.randn(1, length, 256, device="cuda", dtype=torch.bfloat16)
                torch.testing.assert_close(
                    merged(x), torch.cat([layer(x) for layer in layers], dim=-1), atol=0, rtol=0
                )

    def test_native_norm_matches_bf16_reference(self):
        norm = NativeRMSNorm((256,), eps=1e-6, device="cuda", dtype=torch.bfloat16)
        norm.weight.data.copy_(torch.randn_like(norm.weight) * 0.05)
        with torch.inference_mode():
            x = torch.randn(2, 8, 256, device="cuda", dtype=torch.bfloat16)
            expected = (
                x.float()
                * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + 1e-6)
                * (1 + norm.weight.float())
            ).to(x.dtype)
            torch.testing.assert_close(norm(x), expected, atol=0.015625, rtol=0.01)

    def test_fused_delta_matches_reference(self):
        torch.manual_seed(42)
        config = Qwen3_5TextConfig(
            hidden_size=256,
            intermediate_size=512,
            num_hidden_layers=1,
            layer_types=["linear_attention"],
            linear_num_key_heads=2,
            linear_num_value_heads=2,
            linear_key_head_dim=128,
            linear_value_head_dim=128,
        )
        reference = Qwen3_5GatedDeltaNet(config, 0).to(device="cuda", dtype=torch.bfloat16).eval()
        native = NativeDeltaNet(config, 0).to(device="cuda", dtype=torch.bfloat16).eval()
        native.load_state_dict(reference.state_dict())
        native.qkvz = None
        caches = [DynamicCache(config=config), DynamicCache(config=config)]
        with torch.inference_mode():
            x = torch.randn(1, 8, 256, device="cuda", dtype=torch.bfloat16)
            a = reference(x, caches[0])
            b = native(x, caches[1])
            torch.testing.assert_close(a, b, atol=0, rtol=0)
            for _ in range(4):
                x = torch.randn(1, 1, 256, device="cuda", dtype=torch.bfloat16)
                a, b = reference(x, caches[0]), native(x, caches[1])
                self.assertLess((a.float() - b.float()).norm().item() / a.float().norm().item(), 0.02)
                torch.testing.assert_close(
                    caches[0].layers[0].conv_states[0], caches[1].layers[0].conv_states[0], rtol=0, atol=0
                )


if __name__ == "__main__":
    unittest.main()
