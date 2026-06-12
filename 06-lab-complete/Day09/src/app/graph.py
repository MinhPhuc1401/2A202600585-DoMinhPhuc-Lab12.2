from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import operator
from collections import defaultdict

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph

from app.config import Settings
from app.state import ShoppingState
from app.prompts import (
    SUPERVISOR_PROMPT,
    POLICY_WORKER_PROMPT,
    DATA_WORKER_PROMPT,
    RESPONSE_WORKER_PROMPT
)
from app.utils import timestamp_utc, extract_json_payload, dump_json


def run_agent_with_tools(
    model: BaseChatModel,
    tools: list,
    system_prompt: str,
    user_message: str
) -> tuple[str, list[dict[str, Any]]]:
    model_with_tools = model.bind_tools(tools) if tools else model
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]
    
    tool_map = {t.name: t for t in tools}
    tool_calls_trace = []
    
    for _ in range(5):
        response = model_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            return response.content, tool_calls_trace
            
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    pass
                    
            if name in tool_map:
                try:
                    tool_output = tool_map[name].invoke(args)
                except Exception as e:
                    tool_output = f"Error executing tool: {e}"
            else:
                tool_output = f"Tool '{name}' not found."
                
            tool_calls_trace.append({
                "tool_name": name,
                "arguments": args,
                "output": tool_output,
                "timestamp": timestamp_utc()
            })
            
            messages.append(ToolMessage(
                content=str(tool_output),
                name=name,
                tool_call_id=tool_call_id
            ))
            
    return response.content, tool_calls_trace


class ShoppingAssistant:
    """Central Shopping Assistant Graph Orchestration."""
    
    _instance: ShoppingAssistant | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        ShoppingAssistant._instance = self
        self.settings = settings or Settings.load()

        # 1. Load Chat Model
        from provider import get_chat_model
        self.model = get_chat_model(self.settings)

        # 2. Load Dataset
        from app.data_access import ShoppingDataStore
        self.store = ShoppingDataStore(self.settings.orders_path)

        # 3. Load Vector Store
        from rag.embeddings import SentenceTransformerEmbeddings
        from rag.vector_store import ChromaPolicyStore
        self.embeddings = SentenceTransformerEmbeddings(self.settings.embedding_model_name)
        self.policy_store = ChromaPolicyStore(
            persist_directory=self.settings.chroma_dir,
            embedding_model=self.embeddings
        )

        # 4. Build Worker Tools
        from app.data_access import build_data_tools
        self.data_tools = build_data_tools(self.store)

        # 5. Compile LangGraph
        self.graph = build_graph(self)

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)
        else:
            self.policy_store.ensure_index(self.settings.policy_path)
            
        initial_state = {
            "question": question,
            "trace": []
        }
        
        final_state = self.graph.invoke(initial_state)
        
        result = {
            "route": final_state.get("route", {}),
            "policy_result": final_state.get("policy_result", {}),
            "data_result": final_state.get("data_result", {}),
            "final_answer": final_state.get("final_answer", ""),
            "trace": final_state.get("trace", [])
        }
        
        if trace_file:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
        return result

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        traces_dir = output_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)
        else:
            self.policy_store.ensure_index(self.settings.policy_path)
            
        with open(test_file, "r", encoding="utf-8") as f:
            test_cases = json.load(f)
            
        summary_cases = []
        route_correct_count = 0
        status_correct_count = 0
        
        for case in test_cases:
            qid = case.get("id")
            question = case.get("question")
            expected_route = case.get("expected_route", [])
            expected_status = case.get("expected_status", "ok")
            
            print(f"Running query {qid}: {question}")
            
            trace_path = traces_dir / f"{qid}_trace.json"
            result = self.ask(question, trace_file=trace_path)
            
            # Evaluate Route
            actual_route = []
            route_info = result.get("route", {})
            if route_info.get("needs_data"):
                actual_route.append("data")
            if route_info.get("needs_policy"):
                actual_route.append("policy")
                
            route_match = set(actual_route) == set(expected_route)
            if route_match:
                route_correct_count += 1
                
            # Evaluate Status
            final_answer = result.get("final_answer", "")
            if "Status: clarification_needed" in final_answer:
                actual_status = "clarification_needed"
            elif "Status: not_found" in final_answer:
                actual_status = "not_found"
            else:
                actual_status = "ok"
                
            status_match = actual_status == expected_status
            if status_match:
                status_correct_count += 1
                
            summary_cases.append({
                "id": qid,
                "question": question,
                "expected_route": expected_route,
                "actual_route": actual_route,
                "route_match": route_match,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "status_match": status_match,
                "final_answer": final_answer
            })
            
        summary = {
            "total": len(test_cases),
            "route_correct": route_correct_count,
            "status_correct": status_correct_count,
            "cases": summary_cases
        }
        
        summary_path = output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        print(f"Batch run complete. Summary saved to {summary_path}")
        print(f"Route Accuracy: {route_correct_count}/{len(test_cases)} ({route_correct_count/len(test_cases)*100:.2f}%)")
        print(f"Status Accuracy: {status_correct_count}/{len(test_cases)} ({status_correct_count/len(test_cases)*100:.2f}%)")
        
        return summary


def build_graph(assistant: ShoppingAssistant) -> Any:
    workflow = StateGraph(ShoppingState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("worker_1_policy", worker_1_policy_node)
    workflow.add_node("worker_2_data", worker_2_data_node)
    workflow.add_node("worker_3_response", worker_3_response_node)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "worker_1_policy": "worker_1_policy",
            "worker_2_data": "worker_2_data",
            "worker_3_response": "worker_3_response"
        }
    )
    
    # Add simple transitions to join at worker_3_response
    workflow.add_edge("worker_1_policy", "worker_3_response")
    workflow.add_edge("worker_2_data", "worker_3_response")
    
    # Set finish point
    workflow.set_finish_point("worker_3_response")
    
    return workflow.compile()


def route_after_supervisor(state: ShoppingState) -> list[str] | str:
    route = state.get("route", {})
    status = route.get("status")
    if status == "clarification_needed":
        return "worker_3_response"
        
    needs_policy = route.get("needs_policy", False)
    needs_data = route.get("needs_data", False)
    
    destinations = []
    if needs_policy:
        destinations.append("worker_1_policy")
    if needs_data:
        destinations.append("worker_2_data")
        
    if not destinations:
        return "worker_3_response"
        
    return destinations


def supervisor_node(state: ShoppingState) -> ShoppingState:
    assistant = ShoppingAssistant._instance
    prompt = SUPERVISOR_PROMPT
    question = state["question"]
    
    response = assistant.model.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=question)
    ])
    
    route_data = extract_json_payload(response.content)
    
    if "status" not in route_data:
        route_data["status"] = "ok"
    if "needs_policy" not in route_data:
        route_data["needs_policy"] = False
    if "needs_data" not in route_data:
        route_data["needs_data"] = False
    if "clarification_question" not in route_data:
        route_data["clarification_question"] = None
        
    if route_data.get("status") == "clarification_needed":
        route_data["needs_policy"] = False
        route_data["needs_data"] = False
        
    trace_entry = {
        "node": "supervisor",
        "timestamp": timestamp_utc(),
        "input": question,
        "output": route_data
    }
    
    return {
        "route": route_data,
        "trace": [trace_entry]
    }


def worker_1_policy_node(state: ShoppingState) -> ShoppingState:
    assistant = ShoppingAssistant._instance
    question = state["question"]
    
    @tool
    def search_policy(query: str) -> str:
        """Tìm kiếm chính sách mua sắm, giao hàng, đổi trả và voucher của cửa hàng dựa trên truy vấn query."""
        hits = assistant.policy_store.search(query, top_k=assistant.settings.top_k)
        return json.dumps(hits, ensure_ascii=False)
        
    content, tool_calls = run_agent_with_tools(
        model=assistant.model,
        tools=[search_policy],
        system_prompt=POLICY_WORKER_PROMPT,
        user_message=question
    )
    
    policy_result = extract_json_payload(content)
    
    if "status" not in policy_result:
        policy_result["status"] = "ok"
    if "summary" not in policy_result:
        policy_result["summary"] = content
    if "facts" not in policy_result:
        policy_result["facts"] = []
    if "citations" not in policy_result:
        policy_result["citations"] = []
        
    trace_entry = {
        "node": "worker_1_policy",
        "timestamp": timestamp_utc(),
        "input": question,
        "tool_calls": tool_calls,
        "policy_result": policy_result
    }
    
    return {
        "policy_result": policy_result,
        "trace": [trace_entry]
    }


def worker_2_data_node(state: ShoppingState) -> ShoppingState:
    assistant = ShoppingAssistant._instance
    question = state["question"]
    
    content, tool_calls = run_agent_with_tools(
        model=assistant.model,
        tools=assistant.data_tools,
        system_prompt=DATA_WORKER_PROMPT,
        user_message=question
    )
    
    data_result = extract_json_payload(content)
    
    if "status" not in data_result:
        data_result["status"] = "ok"
    if "summary" not in data_result:
        data_result["summary"] = content
    if "facts" not in data_result:
        data_result["facts"] = []
    if "missing_fields" not in data_result:
        data_result["missing_fields"] = []
    if "not_found_entities" not in data_result:
        data_result["not_found_entities"] = []
        
    trace_entry = {
        "node": "worker_2_data",
        "timestamp": timestamp_utc(),
        "input": question,
        "tool_calls": tool_calls,
        "data_result": data_result
    }
    
    return {
        "data_result": data_result,
        "trace": [trace_entry]
    }


def worker_3_response_node(state: ShoppingState) -> ShoppingState:
    assistant = ShoppingAssistant._instance
    question = state.get("question", "")
    route = state.get("route", {})
    policy_result = state.get("policy_result", {})
    data_result = state.get("data_result", {})
    
    prompt = RESPONSE_WORKER_PROMPT.format(
        question=question,
        route=json.dumps(route, ensure_ascii=False, indent=2),
        policy_result=json.dumps(policy_result, ensure_ascii=False, indent=2) if policy_result else "Không có",
        data_result=json.dumps(data_result, ensure_ascii=False, indent=2) if data_result else "Không có"
    )
    
    response = assistant.model.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Hãy tổng hợp câu trả lời theo đúng định dạng bắt buộc.")
    ])
    
    final_answer = response.content.strip()
    
    trace_entry = {
        "node": "worker_3_response",
        "timestamp": timestamp_utc(),
        "final_answer": final_answer
    }
    
    return {
        "final_answer": final_answer,
        "trace": [trace_entry]
    }
