"""
Challenge 1: Build Agents — SDK Track
Anomaly Detection Agent and Fault Diagnosis Agent for TireForge Industries.

Usage:
    python agents.py

Builds both agents with system prompts, tools, and conversation handling.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition, FileSearchTool
from azure.identity import DefaultAzureCredential
from openai.types.responses.response_input_param import FunctionCallOutput


# Resolve repo root by finding .env in parent directories.
def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").exists():
            return parent
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _find_repo_root()

# Load environment
env_path = REPO_ROOT / ".env"
load_dotenv(env_path)

PROJECT_CONNECTION_STRING = os.getenv("PROJECT_CONNECTION_STRING")
MODEL_DEPLOYMENT_NAME = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
SENSOR_DATA_PATH = Path(__file__).resolve().parent / "sensor_data.json"


def _load_sensor_batch() -> list[dict]:
    """Load machine data to send as a batch payload in demo requests."""
    with open(SENSOR_DATA_PATH, "r") as f:
        data = json.load(f)
    return data.get("machines", [])


# =============================================================================
# Tool Function: check_thresholds
# Agents can call this to get threshold analysis
# =============================================================================

def check_thresholds(machine_id: str) -> str:
    """
    Reads sensor_data.json and checks if a machine's readings are within thresholds.
    Returns a JSON string with the analysis.
    """
    with open(SENSOR_DATA_PATH, "r") as f:
        data = json.load(f)

    machine = None
    for m in data["machines"]:
        if m["machine_id"] == machine_id or m["name"] == machine_id:
            machine = m
            break

    if not machine:
        return json.dumps({"error": f"Machine '{machine_id}' not found"})

    results = {
        "machine_id": machine["machine_id"],
        "name": machine["name"],
        "status": machine["status"],
        "last_maintenance": machine["last_maintenance"],
        "anomalies": [],
        "all_readings": {},
    }

    for sensor, reading in machine["readings"].items():
        value = reading["value"]
        threshold = machine["thresholds"][sensor]
        in_spec = threshold["min"] <= value <= threshold["max"]

        results["all_readings"][sensor] = {
            "value": value,
            "unit": reading["unit"],
            "min": threshold["min"],
            "max": threshold["max"],
            "in_spec": in_spec,
        }

        if not in_spec:
            deviation = ""
            if value > threshold["max"]:
                pct = ((value - threshold["max"]) / threshold["max"]) * 100
                deviation = f"{pct:.1f}% above max"
            elif value < threshold["min"]:
                pct = ((threshold["min"] - value) / threshold["min"]) * 100
                deviation = f"{pct:.1f}% below min"

            results["anomalies"].append({
                "sensor": sensor,
                "value": value,
                "unit": reading["unit"],
                "threshold_min": threshold["min"],
                "threshold_max": threshold["max"],
                "deviation": deviation,
            })

    return json.dumps(results, indent=2)


# Tool definition for the agent (Foundry FunctionTool format)
CHECK_THRESHOLDS_TOOL = FunctionTool(
    name="check_thresholds",
    description="Check if a machine's sensor readings are within normal operating thresholds. Returns anomalies if any readings are out of spec.",
    parameters={
        "type": "object",
        "properties": {
            "machine_id": {
                "type": "string",
                "description": "The machine ID (e.g., 'MX-001') or name (e.g., 'mixer') to check",
            }
        },
        "required": ["machine_id"],
        "additionalProperties": False,
    },
    strict=False,
)
# =============================================================================
# Upload Manual to Vector Store
# =============================================================================

def upload_manual_to_vector_store(client: "AIProjectClient", file_path: str) -> str:
    """Uploads a file to the project's vector store and returns the file ID."""
    file = client.agents.upload_file(file_path=file_path)
    print(f"✅ Uploaded manual: {file_path} (ID: {file.id})")
    return file.id

# =============================================================================
# Tool Function: fetch_maintenance_history
# =============================================================================

def fetch_maintenance_history(machine_id: str) -> str:
    """Queries the CMMS for past maintenance records of a machine."""
    with open(REPO_ROOT / "maintenance_history.json", "r") as f:
        history = json.load(f)
    
    # Return history or a message if none exists
    return json.dumps(history.get(machine_id, "No past maintenance history found."))

# Tool definition for the agent (Foundry FunctionTool format)
FETCH_HISTORY_TOOL = FunctionTool(
    name="fetch_maintenance_history",
    description="Retrieve the past maintenance history for a specific machine to inform diagnosis.",
    parameters={
        "type": "object",
        "properties": {
            "machine_id": {"type": "string", "description": "The machine ID"}
        },
        "required": ["machine_id"],
    },
)

# =============================================================================
# Tool Function: lookup_spare_parts
# =============================================================================
def lookup_spare_parts(part_number: str) -> str:
    """Queries the ERP/Inventory system for spare part availability."""
    inventory_file = REPO_ROOT / "inventory.json"
    
    if not inventory_file.exists():
        return json.dumps({"error": "Inventory database unavailable."})
        
    with open(inventory_file, "r") as f:
        inventory = json.load(f)
    
    # Strip any potential '#' symbol the agent might pass
    clean_part_number = part_number.replace("#", "").strip()
    
    part_info = inventory.get(clean_part_number)
    
    if part_info:
        return json.dumps(part_info)
    else:
        return json.dumps({"status": "UNKNOWN_PART", "message": f"Part {clean_part_number} not found in inventory system."})

LOOKUP_PARTS_TOOL = FunctionTool(
    name="lookup_spare_parts",
    description="Check the inventory availability of a specific spare part. Requires the exact part number (e.g., TF-101).",
    parameters={
        "type": "object",
        "properties": {
            "part_number": {"type": "string", "description": "The exact part number to look up"}
        },
        "required": ["part_number"],
        "additionalProperties": False,
    },
    strict=False,
)

# =============================================================================
# Tool Function: create_work_order
# =============================================================================
def create_work_order(machine_id: str, action: str, urgency: str) -> str:
    """Creates a maintenance work order in the CMMS after approval."""
    work_order_file = REPO_ROOT / "work_orders.json"
    
    # Create an ID for the work order
    import random
    wo_id = f"WO-{random.randint(10000, 99999)}"
    
    order_data = {
        "work_order_id": wo_id,
        "machine_id": machine_id,
        "required_action": action,
        "urgency": urgency,
        "status": "OPEN",
        "created_at": "2026-07-15"
    }
    
    # Load existing or start fresh
    orders = []
    if work_order_file.exists():
        with open(work_order_file, "r") as f:
            try:
                orders = json.load(f)
            except json.JSONDecodeError:
                pass
                
    orders.append(order_data)
    
    with open(work_order_file, "w") as f:
        json.dump(orders, f, indent=2)
        
    return json.dumps({"status": "SUCCESS", "work_order_id": wo_id, "message": f"Work order {wo_id} created successfully."})

# =============================================================================
# Anomaly Detection Agent
# =============================================================================

class AnomalyDetectionAgent:
    def __init__(self):
        self.agent = None
        self.client = None
        self.openai = None

    def create(self):
        """Create the anomaly detection agent in Foundry."""
        self.client = AIProjectClient(
            endpoint=PROJECT_CONNECTION_STRING,
            credential=DefaultAzureCredential(),
        )
        self.openai = self.client.get_openai_client()

        system_prompt = """
        You are an industrial sensor anomaly detection expert for TireForge Industries.
        When asked to check machines, use the check_thresholds tool for each machine.
        For each machine, report:
        - Machine name and ID
        - Status (normal / warning / critical)
        - Each sensor reading that is out of spec: current value, threshold violated, deviation
        Use ⚠️ for warning and 🔴 for critical anomalies.
        If all readings are in spec, mark the machine as normal.
        Be concise and structured.
        """

        self.agent = self.client.agents.create_version(
            agent_name="anomaly-detection-agent",
            definition=PromptAgentDefinition(
                model=MODEL_DEPLOYMENT_NAME,
                instructions=system_prompt,
                tools=[CHECK_THRESHOLDS_TOOL],
            ),
        )

        return self.agent

    def run(self, input_text: str) -> str:
        """Run the anomaly detection agent with the given input."""
        conversation = self.openai.conversations.create()

        response = self.openai.responses.create(
            input=input_text,
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": self.agent.name, "type": "agent_reference"}},
        )

        # Handle function call loops
        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            input_list = []
            for item in function_calls:
                if item.name == "check_thresholds":
                    args = json.loads(item.arguments)
                    result = check_thresholds(args["machine_id"])
                else:
                    result = json.dumps({"error": f"Unknown tool '{item.name}'"})

                input_list.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        call_id=item.call_id,
                        output=result,
                    )
                )

            response = self.openai.responses.create(
                input=input_list,
                conversation=conversation.id,
                extra_body={"agent_reference": {"name": self.agent.name, "type": "agent_reference"}},
            )

        self.openai.conversations.delete(conversation_id=conversation.id)
        return response.output_text

    def cleanup(self):
        """Delete the agent version and close connections."""
        if self.agent:
            self.client.agents.delete_version(
                agent_name=self.agent.name,
                agent_version=self.agent.version,
            )
        if self.client:
            self.client.close()


# =============================================================================
# Fault Diagnosis Agent
# =============================================================================

class FaultDiagnosisAgent:
    def __init__(self):
        self.agent = None
        self.client = None
        self.openai = None

    def create(self):
        """Create the fault diagnosis agent in Foundry."""
        self.client = AIProjectClient(
            endpoint=PROJECT_CONNECTION_STRING,
            credential=DefaultAzureCredential(),
        )
        self.openai = self.client.get_openai_client()

        manual_path = REPO_ROOT / "TireForge_Manual_V2.md"
        file_id = upload_manual_to_vector_store(self.client, str(manual_path))

        rag_tool = FileSearchTool(file_search={"file_ids": [file_id]})

        system_prompt = """
        You are a mechanical fault diagnosis expert for TireForge Industries.
        Given a list of sensor anomalies from a machine, your job is to:
        1. ALWAYS check the maintenance history using the fetch_maintenance_history tool.
        2. Use the File Search tool to ground your answers in official procedures and identify required part numbers.
        3. ALWAYS check inventory for any required parts using the lookup_spare_parts tool.
        4. Identify the most likely root cause.
        5. Recommend specific maintenance steps. If a part is out of stock, suggest an interim workaround or note the delay.
        6. Estimate urgency: IMMEDIATE (stop now), WITHIN 24H, or MONITOR.
        
        CRITICAL RULE: If the urgency is IMMEDIATE, you must end your response with the exact phrase: "REQUIRES_APPROVAL: YES". Otherwise, end with "REQUIRES_APPROVAL: NO".
        
        Format your response as:
        LIKELY CAUSE: ...
        MAINTENANCE ACTIONS: ...
        PART AVAILABILITY: ...
        URGENCY: ...
        REQUIRES_APPROVAL: ...
        """

        self.agent = self.client.agents.create_version(
            agent_name="fault-diagnosis-agent",
            definition=PromptAgentDefinition(
                model=MODEL_DEPLOYMENT_NAME,
                instructions=system_prompt,
                tools=[rag_tool, FETCH_HISTORY_TOOL, LOOKUP_PARTS_TOOL],
            ),
        )

        return self.agent

    def run(self, input_text: str) -> str:
        """Run the fault diagnosis agent, handling tool calls (RAG/Function) if needed."""
        conversation = self.openai.conversations.create()

        response = self.openai.responses.create(
            input=input_text,
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": self.agent.name, "type": "agent_reference"}},
        )
        # Handle function /tool call loops
        while True:
            # Check if the agent wants to call a tool
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break
            
            input_list = []
            for item in function_calls:
                # if the tool is file_search, use the file_search tool to search the files
                if item.name == "fetch_maintenance_history":
                    args = json.loads(item.arguments)
                    result = fetch_maintenance_history(args["machine_id"])
                elif item.name == "lookup_spare_parts":
                    args = json.loads(item.arguments)
                    result = lookup_spare_parts(args["part_number"])
                else:
                    result = json.dumps({"status": "Tool handled by agent service"})

                input_list.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        call_id=item.call_id,
                        output=result,
                    )
                )

            response = self.openai.responses.create(
                input=input_list,
                conversation=conversation.id,
                extra_body={"agent_reference": {"name": self.agent.name, "type": "agent_reference"}},
            )

        self.openai.conversations.delete(conversation_id=conversation.id)
        return response.output_text

    def cleanup(self):
        """Delete the agent version and close connections."""
        if self.agent:
            self.client.agents.delete_version(
                agent_name=self.agent.name,
                agent_version=self.agent.version,
            )
        if self.client:
            self.client.close()


# =============================================================================
# Main — Test both agents
# =============================================================================

def main():
    if not PROJECT_CONNECTION_STRING:
        print("❌ PROJECT_CONNECTION_STRING not set. Run challenge 0 first!")
        sys.exit(1)

    print("=== Anomaly Detection Agent ===")
    print("Creating agent...")

    anomaly_agent = AnomalyDetectionAgent()
    anomaly_agent.create()
    print(f"✅ Created: {anomaly_agent.agent.name} (version {anomaly_agent.agent.version})")

    print("\nAnalyzing all machines...")
    machine_batch = _load_sensor_batch()
    machine_ids = [machine["machine_id"] for machine in machine_batch]
    anomaly_result = anomaly_agent.run(
        "You are receiving a batch payload of machines that must be processed in one run. "
        "Use check_thresholds for each machine_id in the payload and return the anomaly summary.\n\n"
        f"BATCH_MACHINE_IDS: {json.dumps(machine_ids)}\n"
        "BATCH_MACHINE_DATA:\n"
        f"{json.dumps(machine_batch, indent=2)}"
    )
    print(anomaly_result)

    print("\n=== Fault Diagnosis Agent ===")
    print("Creating agent...")

    diagnosis_agent = FaultDiagnosisAgent()
    diagnosis_agent.create()
    print(f"✅ Created: {diagnosis_agent.agent.name} (version {diagnosis_agent.agent.version})")

    print("\nDiagnosing critical machine: curing_press...")
    critical_batch = [machine for machine in machine_batch if machine["status"] in {"critical", "warning"}]
    
    diagnosis_result = diagnosis_agent.run(
        "Diagnose the following critical-machine batch and provide root cause, "
        "maintenance actions, and urgency for each entry.\n\n"
        "CRITICAL_MACHINE_BATCH:\n"
        f"{json.dumps(critical_batch, indent=2)}"
    )
    print("\n=== DIAGNOSIS REPORT ===")
    print(diagnosis_result)
    print("========================\n")

    # --- HUMAN IN THE LOOP LOGIC ---
    if "REQUIRES_APPROVAL: YES" in diagnosis_result:
        print("⚠️ CRITICAL ACTION DETECTED. Human approval required to proceed with Work Order.")
        user_input = input("Approve this maintenance action? (y/n): ")
        
        if user_input.lower().strip() == 'y':
            print("Processing approval...")
            # For this demo, we extract the action text or pass the critical batch machine info
            for machine in critical_batch:
                if machine["status"] == "critical":
                    # Call the tool to create a record in your local work_orders.json
                    wo_result = create_work_order(
                        machine_id=machine["machine_id"],
                        action="Execute diagnostic maintenance based on AI manual recommendation",
                        urgency="IMMEDIATE"
                    )
                    print(f"✅ Tool Output: {wo_result}")
        else:
            print("❌ Action Rejected. Escalating to shift supervisor.")
    else:
        print("ℹ️ No immediate action required. Logging to maintenance queue.")
        

    # Cleanup — comment out to keep agents visible in the Foundry portal
    # print("\nCleaning up agents...")
    # anomaly_agent.cleanup()
    # diagnosis_agent.cleanup()
    # print("✅ Done!")


if __name__ == "__main__":
    main()
