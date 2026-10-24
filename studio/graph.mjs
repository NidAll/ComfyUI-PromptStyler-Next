/** Place one shared-engine node at an explicitly mapped native text input. */
export function injectPromptStyler(graph, workflow, body) {
  const recipe = body.promptStyler;
  if (!recipe?.styles?.length) return graph;
  const target = workflow.promptStyler || workflow.controls?.prompt;
  if (!target?.node || !target?.input || !graph[target.node]?.inputs || !(target.input in graph[target.node].inputs)) {
    throw new Error('This workflow has no PromptStyler text target. Map its native prompt input first.');
  }
  const input = graph[target.node].inputs[target.input];
  if (typeof input !== 'string' && !(Array.isArray(input) && input.length === 2 && typeof input[0] === 'string' && Number.isInteger(input[1]))) {
    throw new Error('The PromptStyler target must contain text or a native text link.');
  }
  let id = 'promptstyler_next';
  for (let index = 1; graph[id]; index += 1) id = `promptstyler_next_${index}`;
  graph[id] = {
    class_type: 'PSNextCompose',
    inputs: { recipe: JSON.stringify({ ...recipe, prompt: '', negative: body.negative || '' }), prompt: input },
    _meta: { title: 'PromptStyler Next' },
  };
  graph[target.node].inputs[target.input] = [id, 0];
  const negative = workflow.controls?.negative;
  if (negative?.node && negative?.input && graph[negative.node]?.inputs) graph[negative.node].inputs[negative.input] = [id, 1];
  return graph;
}
