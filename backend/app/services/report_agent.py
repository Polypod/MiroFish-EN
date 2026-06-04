"""
Report Agent service.
Uses LLM + Zep to generate simulation reports in ReACT mode.

Features:
1. Generate reports based on simulation requirements and Zep graph data.
2. Plan the report outline first, then generate section by section.
3. Use multi-round ReACT reasoning and reflection for each section.
4. Support user chat and autonomous retrieval tool calls during conversation.
"""

import os
import json
import re
import uuid
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)
from .report_manager import (
    ReportManager,
    ReportStatus,
    ReportSection,
    ReportOutline,
    Report,
)
from .report_prompts import (
    TOOL_DESC_INSIGHT_FORGE,
    TOOL_DESC_PANORAMA_SEARCH,
    TOOL_DESC_QUICK_SEARCH,
    TOOL_DESC_INTERVIEW_AGENTS,
    PLAN_SYSTEM_PROMPT,
    PLAN_USER_PROMPT_TEMPLATE,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
    REACT_OBSERVATION_TEMPLATE,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    REACT_FORCE_FINAL_MSG,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    CHAT_OBSERVATION_SUFFIX,
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Detailed logger for Report Agent.

    Creates `agent_log.jsonl` in the report folder and records each step.
    """
    
    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(self, action: str, stage: str, details: Dict[str, Any],
            section_title: str = None, section_index: int = None):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        self.log("report_start", "pending", {
            "simulation_id": simulation_id, "graph_id": graph_id,
            "simulation_requirement": simulation_requirement,
            "message": "Report generation started"
        })
    
    def log_planning_start(self):
        self.log("planning_start", "planning", {"message": "Started planning report outline"})
    
    def log_planning_context(self, context: Dict[str, Any]):
        self.log("planning_context", "planning", {"message": "Retrieved simulation context", "context": context})
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        self.log("planning_complete", "planning", {"message": "Outline planning completed", "outline": outline_dict})
    
    def log_section_start(self, section_title: str, section_index: int):
        self.log("section_start", "generating", {"message": f"Started generating section: {section_title}"},
                 section_title=section_title, section_index=section_index)
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        self.log("react_thought", "generating",
                 {"iteration": iteration, "thought": thought, "message": f"ReACT reasoning round {iteration}"},
                 section_title=section_title, section_index=section_index)
    
    def log_tool_call(self, section_title: str, section_index: int, tool_name: str, 
                      parameters: Dict[str, Any], iteration: int):
        self.log("tool_call", "generating",
                 {"iteration": iteration, "tool_name": tool_name, "parameters": parameters,
                  "message": f"Tool called: {tool_name}"},
                 section_title=section_title, section_index=section_index)
    
    def log_tool_result(self, section_title: str, section_index: int, tool_name: str,
                        result: str, iteration: int):
        self.log("tool_result", "generating",
                 {"iteration": iteration, "tool_name": tool_name, "result": result,
                  "result_length": len(result), "message": f"Tool {tool_name} returned result"},
                 section_title=section_title, section_index=section_index)
    
    def log_llm_response(self, section_title: str, section_index: int, response: str,
                         iteration: int, has_tool_calls: bool, has_final_answer: bool):
        self.log("llm_response", "generating",
                 {"iteration": iteration, "response": response, "response_length": len(response),
                  "has_tool_calls": has_tool_calls, "has_final_answer": has_final_answer,
                  "message": f"LLM response (tool_calls: {has_tool_calls}, final_answer: {has_final_answer})"},
                 section_title=section_title, section_index=section_index)
    
    def log_section_content(self, section_title: str, section_index: int, content: str, tool_calls_count: int):
        self.log("section_content", "generating",
                 {"content": content, "content_length": len(content),
                  "tool_calls_count": tool_calls_count,
                  "message": f"Section {section_title} content generation completed"},
                 section_title=section_title, section_index=section_index)
    
    def log_section_full_complete(self, section_title: str, section_index: int, full_content: str):
        self.log("section_complete", "generating",
                 {"content": full_content, "content_length": len(full_content),
                  "message": f"Section {section_title} generation completed"},
                 section_title=section_title, section_index=section_index)
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        self.log("report_complete", "completed",
                 {"total_sections": total_sections, "total_time_seconds": round(total_time_seconds, 2),
                  "message": "Report generation completed"})
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        self.log("error", stage, {"error": error_message, "message": f"Error occurred: {error_message}"},
                 section_title=section_title)


class ReportConsoleLogger:
    """Console-style logger for Report Agent. Writes to console_log.txt."""
    
    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
        self._file_handler = None
        self._setup_file_handler()
    
    def _setup_file_handler(self):
        import logging
        self._file_handler = logging.FileHandler(self.log_file_path, mode='a', encoding='utf-8')
        self._file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
        self._file_handler.setFormatter(formatter)
        for name in ['mirofish.report_agent', 'mirofish.zep_tools']:
            target = logging.getLogger(name)
            if self._file_handler not in target.handlers:
                target.addHandler(self._file_handler)
    
    def close(self):
        import logging
        if self._file_handler:
            for name in ['mirofish.report_agent', 'mirofish.zep_tools']:
                target = logging.getLogger(name)
                if self._file_handler in target.handlers:
                    target.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        self.close()


# ═══════════════════════════════════════════════════════════════
# ReportAgent main class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - simulation report generation agent.

    Uses ReACT (Reasoning + Acting):
    1. Planning stage: analyze simulation requirements and build an outline.
    2. Generation stage: write sections one by one with tool-assisted retrieval.
    3. Reflection stage: check completeness and accuracy.
    """
    
    MAX_TOOL_CALLS_PER_SECTION = 5
    MAX_REFLECTION_ROUNDS = 3
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        self.tools = self._define_tools()
        self.report_logger: Optional[ReportLogger] = None
        self.console_logger: Optional[ReportConsoleLogger] = None
        logger.info(f"ReportAgent initialized: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "Question or topic to analyze deeply",
                    "report_context": "Current section context (optional)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query used for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description",
                    "max_agents": "Maximum number of agents to interview (optional, default 5, max 10)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        logger.info(f"Execute tool: {tool_name}, params: {parameters}")
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                return self.zep_tools.insight_forge(
                    graph_id=self.graph_id, query=query,
                    simulation_requirement=self.simulation_requirement, report_context=ctx
                ).to_text()
            elif tool_name == "panorama_search":
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                return self.zep_tools.panorama_search(
                    graph_id=self.graph_id, query=query, include_expired=include_expired
                ).to_text()
            elif tool_name == "quick_search":
                query = parameters.get("query", "")
                limit = int(parameters.get("limit", 10)) if isinstance(parameters.get("limit"), str) else parameters.get("limit", 10)
                return self.zep_tools.quick_search(
                    graph_id=self.graph_id, query=query, limit=limit
                ).to_text()
            elif tool_name == "interview_agents":
                topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = min(int(parameters.get("max_agents", 5)) if isinstance(parameters.get("max_agents"), str) else parameters.get("max_agents", 5), 10)
                return self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id, interview_requirement=topic,
                    simulation_requirement=self.simulation_requirement, max_agents=max_agents
                ).to_text()
            # Legacy redirects
            elif tool_name == "search_graph":
                return self._execute_tool("quick_search", parameters, report_context)
            elif tool_name == "get_graph_statistics":
                return json.dumps(self.zep_tools.get_graph_statistics(self.graph_id), ensure_ascii=False, indent=2)
            elif tool_name == "get_entity_summary":
                return json.dumps(self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id, entity_name=parameters.get("entity_name", "")
                ), ensure_ascii=False, indent=2)
            elif tool_name == "get_simulation_context":
                return self._execute_tool("insight_forge", {"query": parameters.get("query", self.simulation_requirement)}, report_context)
            elif tool_name == "get_entities_by_type":
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id, entity_type=parameters.get("entity_type", "")
                )
                return json.dumps([n.to_dict() for n in nodes], ensure_ascii=False, indent=2)
            else:
                return f"Unknown tool: {tool_name}. Use one of: insight_forge, panorama_search, quick_search"
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"
    
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        tool_calls = []

        # Format 1: XML style
        for match in re.finditer(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', response, re.DOTALL):
            try:
                tool_calls.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass
        if tool_calls:
            return tool_calls

        # Format 2: bare JSON
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    return [call_data]
            except json.JSONDecodeError:
                pass

        # Last JSON object in response
        match = re.search(r'(\{"(?:name|tool)"\s*:.*?\})\s*$', stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(self, progress_callback: Optional[Callable] = None) -> ReportOutline:
        logger.info("Start planning report outline...")
        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")
        
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id, simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")
            
            sections = [ReportSection(title=s.get("title", "")) for s in response.get("sections", [])]
            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Outline planning completed")
            
            logger.info(f"Outline planning completed: {len(sections)} sections")
            return outline
            
        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            return ReportOutline(
                title="Future Prediction Report",
                summary="Future trend and risk analysis based on simulation predictions",
                sections=[
                    ReportSection(title="Predicted Scenario and Core Findings"),
                    ReportSection(title="Crowd Behavior Prediction Analysis"),
                    ReportSection(title="Trend Outlook and Risk Signals")
                ]
            )
    
    def _generate_section_react(
        self, section: ReportSection, outline: ReportOutline,
        previous_sections: List[str], progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        logger.info(f"ReACT generating section: {section.title}")
        
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title, report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title, tools_description=self._get_tools_description(),
        )

        if previous_sections:
            previous_content = "\n\n---\n\n".join(
                s[:4000] + "..." if len(s) > 4000 else s for s in previous_sections
            )
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content, section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        tool_calls_count = 0
        max_iterations = 5
        min_tool_calls = 3
        conflict_retries = 0
        used_tools = set()
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing in progress ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            response = self.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)

            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(empty response)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                break

            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # Conflict handling
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                if conflict_retries <= 2:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        "[Format error] You included both a tool call and Final Answer in one reply.\n"
                        "Each reply can do only one. Please reply again."
                    )})
                    continue
                else:
                    first_end = response.find('</tool_call>')
                    if first_end != -1:
                        response = response[:first_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            if self.report_logger:
                self.report_logger.log_llm_response(
                    section.title, section_index, response, iteration + 1,
                    has_tool_calls, has_final_answer
                )

            # Final Answer
            if has_final_answer:
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused = all_tools - used_tools
                    hint = f"(Unused tools: {', '.join(unused)})" if unused else ""
                    messages.append({"role": "user", "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                        tool_calls_count=tool_calls_count, min_tool_calls=min_tool_calls, unused_hint=hint
                    )})
                    continue
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generated (tool calls: {tool_calls_count})")
                if self.report_logger:
                    self.report_logger.log_section_content(section.title, section_index, final_answer, tool_calls_count)
                return final_answer

            # Tool calls
            if has_tool_calls:
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": REACT_TOOL_LIMIT_MSG.format(
                        tool_calls_count=tool_calls_count, max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION
                    )})
                    continue

                call = tool_calls[0]
                if self.report_logger:
                    self.report_logger.log_tool_call(section.title, section_index, call["name"], call.get("parameters", {}), iteration + 1)

                result = self._execute_tool(call["name"], call.get("parameters", {}), report_context=report_context)

                if self.report_logger:
                    self.report_logger.log_tool_result(section.title, section_index, call["name"], result, iteration + 1)

                tool_calls_count += 1
                used_tools.add(call['name'])
                unused = all_tools - used_tools
                unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused)) if unused and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION else ""

                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": REACT_OBSERVATION_TEMPLATE.format(
                    tool_name=call["name"], result=result, tool_calls_count=tool_calls_count,
                    max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION, used_tools_str=", ".join(used_tools),
                    unused_hint=unused_hint,
                )})
                continue

            # No tool call and no Final Answer
            messages.append({"role": "assistant", "content": response})
            if tool_calls_count < min_tool_calls:
                unused = all_tools - used_tools
                hint = f"(Unused tools: {', '.join(unused)})" if unused else ""
                messages.append({"role": "user", "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                    tool_calls_count=tool_calls_count, min_tool_calls=min_tool_calls, unused_hint=hint
                )})
                continue

            # Accept as final content
            logger.info(f"Section {section.title} has no 'Final Answer:' prefix; accepting as final (tool calls: {tool_calls_count})")
            if self.report_logger:
                self.report_logger.log_section_content(section.title, section_index, response.strip(), tool_calls_count)
            return response.strip()
        
        # Force final generation
        logger.warning(f"Section {section.title} reached max iterations, forcing final generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        response = self.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)

        if response is None:
            final_answer = "(Section generation failed: LLM returned an empty response.)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        if self.report_logger:
            self.report_logger.log_section_content(section.title, section_index, final_answer, tool_calls_count)
        return final_answer
    
    def generate_report(
        self, progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id, simulation_id=self.simulation_id,
            graph_id=self.graph_id, simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING, created_at=datetime.now().isoformat()
        )
        completed_section_titles = []
        
        try:
            ReportManager._ensure_report_folder(report_id)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(self.simulation_id, self.graph_id, self.simulation_requirement)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(report_id, "pending", 0, "Initializing report...", completed_sections=[])
            ReportManager.save_report(report)
            
            # Plan outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(report_id, "planning", 5, "Starting report outline planning...", completed_sections=[])
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Starting report outline planning...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            self.report_logger.log_planning_complete(outline.to_dict())
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(report_id, "planning", 15, f"Outline completed, {len(outline.sections)} sections", completed_sections=[])
            ReportManager.save_report(report)
            
            # Generate sections
            report.status = ReportStatus.GENERATING
            total_sections = len(outline.sections)
            generated_sections = []
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title, completed_sections=completed_section_titles
                )
                if progress_callback:
                    progress_callback("generating", base_progress, f"Generating: {section.title} ({section_num}/{total_sections})")
                
                section_content = self._generate_section_react(
                    section=section, outline=outline, previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg: progress_callback(
                        stage, base_progress + int(prog * 0.7 / total_sections), msg
                    ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)
                
                if self.report_logger:
                    self.report_logger.log_section_full_complete(section.title, section_num, f"## {section.title}\n\n{section_content}")
                
                ReportManager.update_progress(
                    report_id, "generating", base_progress + int(70 / total_sections),
                    f"Section {section.title} completed", current_section=None, completed_sections=completed_section_titles
                )
            
            # Assemble
            if progress_callback:
                progress_callback("generating", 95, "Assembling full report...")
            ReportManager.update_progress(report_id, "generating", 95, "Assembling full report...", completed_sections=completed_section_titles)
            
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            total_time = (datetime.now() - start_time).total_seconds()
            if self.report_logger:
                self.report_logger.log_report_complete(total_sections, total_time)
            
            ReportManager.save_report(report)
            ReportManager.update_progress(report_id, "completed", 100, "Report generation completed", completed_sections=completed_section_titles)
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation completed")
            
            logger.info(f"Report generation completed: {report_id}")
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(report_id, "failed", -1, f"Failed: {str(e)}", completed_sections=completed_section_titles)
            except Exception:
                pass
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            return report
    
    def chat(self, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        logger.info(f"Report Agent chat: {message[:50]}...")
        chat_history = chat_history or []
        
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content or "(No report available yet)",
            tools_description=self._get_tools_description(),
        )

        messages = [{"role": "system", "content": system_prompt}]
        for h in chat_history[-10:]:
            messages.append(h)
        messages.append({"role": "user", "content": message})
        
        tool_calls_made = []
        
        for iteration in range(2):
            response = self.llm.chat(messages=messages, temperature=0.5)
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                clean = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean = re.sub(r'\[TOOL_CALL\].*?\)', '', clean)
                return {
                    "response": clean.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            tool_results = []
            for call in tool_calls[:1]:
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({"tool": call["name"], "result": result[:1500]})
                tool_calls_made.append(call)
            
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({"role": "user", "content": observation + CHAT_OBSERVATION_SUFFIX})
        
        final_response = self.llm.chat(messages=messages, temperature=0.5)
        clean = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean = re.sub(r'\[TOOL_CALL\].*?\)', '', clean)
        return {
            "response": clean.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }
