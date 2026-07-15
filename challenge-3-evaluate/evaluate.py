"""
Phase 3: Evaluate -- SDK Track
Hardcoded, repeatable LLM-as-judge evaluation of the Anomaly Detection Agent.

This replaces the manual "upload a dataset in the Foundry portal and click
through the Evaluation wizard" flow with a script that can run unattended in
CI: it sends every case in eval_portal.jsonl through the deployed agent,
scores each response for coherence and fluency with the Azure AI Evaluation
SDK, and exits non-zero if either aggregate score drops below THRESHOLD --
suitable as a quality gate on every pull request (see
.github/workflows/evaluate.yml).

Usage:
    python evaluate.py
    EVAL_SCORE_THRESHOLD=4.0 python evaluate.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").exists():
            return parent
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _find_repo_root()
load_dotenv(REPO_ROOT / ".env")

PROJECT_CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
FOUNDRY_ENDPOINT = os.getenv("FOUNDRY_ENDPOINT")
MODEL_DEPLOYMENT_NAME = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
ANOMALY_AGENT_NAME = "anomaly-detection-agent"

DATASET_PATH = Path(__file__).resolve().parent / "eval_portal.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "evaluation_results.json"
THRESHOLD = float(os.getenv("EVAL_SCORE_THRESHOLD", "3.5"))


def call_anomaly_agent(query: str, **kwargs) -> dict:
    """Target function for azure.ai.evaluation.evaluate(): sends each eval
    row's query to the deployed anomaly-detection-agent and returns its
    response for scoring.

    Note: the parameter name `**kwargs` (not e.g. `**_ignored`) matters here
    -- the evaluate() SDK inspects this function's signature and only
    special-cases a catch-all parameter literally named `kwargs`.
    """
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    client = AIProjectClient(endpoint=PROJECT_CONNECTION_STRING, credential=DefaultAzureCredential())
    openai_client = client.get_openai_client()
    agent_ref = {"agent_reference": {"name": ANOMALY_AGENT_NAME, "type": "agent_reference"}}

    # Eval rows already embed the machine's readings and thresholds directly
    # in the query text (deliberately different from the live sensor_data.json
    # in most rows), so the agent must reason from the text given rather than
    # calling check_thresholds -- which would substitute today's live sensor
    # values in place of the case being graded.
    prompt = query + "\n\nAnalyse only the data provided above. Do not call check_thresholds."

    conversation = openai_client.conversations.create()
    response = openai_client.responses.create(
        input=prompt,
        conversation=conversation.id,
        extra_body=agent_ref,
    )

    # Defensively drain any function-call turn the model attempts anyway, so
    # a single unexpected tool call can't hang the evaluation run.
    while any(item.type == "function_call" for item in response.output):
        tool_outputs = [
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps({"status": "Tool calls are disabled during evaluation; use the provided data."}),
            }
            for item in response.output
            if item.type == "function_call"
        ]
        response = openai_client.responses.create(
            input=tool_outputs,
            conversation=conversation.id,
            extra_body=agent_ref,
        )

    openai_client.conversations.delete(conversation_id=conversation.id)
    client.close()
    return {"response": response.output_text}


def main():
    if not PROJECT_CONNECTION_STRING:
        print("PROJECT_CONNECTION_STRING not set. Run challenge-0-setup/deploy.sh first!")
        sys.exit(1)
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        sys.exit(1)

    from azure.ai.evaluation import AzureOpenAIModelConfiguration, CoherenceEvaluator, FluencyEvaluator, evaluate
    from azure.identity import DefaultAzureCredential

    # `credential` must be passed to each evaluator directly, not inside
    # model_config -- putting it in model_config trips a validation bug in
    # azure-ai-evaluation 1.18.x (isinstance() against a typing.Any field).
    model_config = AzureOpenAIModelConfiguration(
        azure_endpoint=FOUNDRY_ENDPOINT,
        azure_deployment=MODEL_DEPLOYMENT_NAME,
        api_version=AZURE_OPENAI_API_VERSION,
    )
    credential = DefaultAzureCredential()

    coherence_evaluator = CoherenceEvaluator(model_config=model_config, credential=credential)
    fluency_evaluator = FluencyEvaluator(model_config=model_config, credential=credential)

    case_count = sum(1 for _ in open(DATASET_PATH))
    print(f"=== Running evaluation: {DATASET_PATH.name} ({case_count} test cases) ===")

    result = evaluate(
        data=str(DATASET_PATH),
        target=call_anomaly_agent,
        evaluators={"coherence": coherence_evaluator, "fluency": fluency_evaluator},
        evaluation_name="factory-anomaly-agent-ci",
        output_path=str(RESULTS_PATH),
    )

    metrics = result["metrics"]
    print("\n=== Aggregate metrics ===")
    for name, value in metrics.items():
        print(f"  {name}: {value}")

    coherence_scores = [v for k, v in metrics.items() if "coherence" in k.lower() and isinstance(v, (int, float))]
    fluency_scores = [v for k, v in metrics.items() if "fluency" in k.lower() and isinstance(v, (int, float))]

    if not coherence_scores or not fluency_scores:
        print(f"\nCould not locate coherence/fluency scores in metrics -- see {RESULTS_PATH} for full output.")
        sys.exit(1)

    coherence_avg, fluency_avg = coherence_scores[0], fluency_scores[0]

    print(f"\nThreshold: {THRESHOLD}")
    print(f"  Coherence: {coherence_avg}  {'PASS' if coherence_avg >= THRESHOLD else 'FAIL'}")
    print(f"  Fluency:   {fluency_avg}  {'PASS' if fluency_avg >= THRESHOLD else 'FAIL'}")

    if coherence_avg < THRESHOLD or fluency_avg < THRESHOLD:
        print(f"\n❌ Quality gate failed: a score dropped below {THRESHOLD}.")
        sys.exit(1)

    print(f"\n✅ Quality gate passed: all scores >= {THRESHOLD}.")


if __name__ == "__main__":
    main()
