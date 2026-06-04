"""
OASIS simulation manager.
Manages parallel simulation across Twitter and Reddit.
Uses preset scripts + LLM to intelligently generate configuration parameters.
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger, log_llm_interaction
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters
from .synthetic_delegate_generator import SyntheticDelegateGenerator

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """Simulation status."""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Simulation was stopped manually
    COMPLETED = "completed"  # Simulation completed naturally
    FAILED = "failed"


class PlatformType(str, Enum):
    """Platform type."""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """Simulation state."""
    simulation_id: str
    project_id: str
    graph_id: str
    
    # Platform enablement state
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # Status
    status: SimulationStatus = SimulationStatus.CREATED
    
    # Preparation stage data
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    
    # Configuration generation information
    config_generated: bool = False
    config_reasoning: str = ""
    
    # Runtime data
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Error information
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Full state dictionary (for internal use)."""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Simplified state dictionary (for API responses)."""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Simulation manager.

    Core functionality:
    1. Read and filter entities from Zep graph
    2. Generate OASIS agent profiles
    3. Use LLM to intelligently generate simulation configuration parameters
    4. Prepare all files required by preset scripts
    """
    
    # Simulation data storage directory
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # Ensure directory exists
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # In-memory simulation state cache
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Get simulation data directory."""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Save simulation state to file."""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Load simulation state from file."""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Create a new simulation.

        Args:
            project_id: Project ID
            graph_id: Zep graph ID
            enable_twitter: Whether to enable Twitter simulation
            enable_reddit: Whether to enable Reddit simulation

        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Created simulation: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        enable_synthetic_delegates: bool = True,
        synthetic_delegate_count: int = 30,
        synthetic_delegate_config: Optional[Dict[str, Any]] = None,
    ) -> SimulationState:
        """
        Prepare simulation environment (fully automated).

        Steps:
        1. Read and filter entities from Zep graph
        2. Generate OASIS agent profiles for each entity (optional LLM enhancement, parallel supported)
        3. Use LLM to intelligently generate simulation config parameters (time, activity, posting frequency, etc.)
        4. Save configuration and profile files
        5. Copy preset scripts to simulation directory

        Args:
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description (used for LLM config generation)
            document_text: Raw document content (used by LLM for context understanding)
            defined_entity_types: Predefined entity types (optional)
            use_llm_for_profiles: Whether to use LLM for detailed profile generation
            progress_callback: Progress callback function (stage, progress, message)
            parallel_profile_count: Number of profiles generated in parallel, default 3

        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)

            # ========== Stage 1.5 init — always run regardless of entity count ==========
            synthetic_nodes = []
            synthetic_profiles = []

            # ========== Stage 1: Read and filter entities ==========
            if progress_callback:
                progress_callback("reading", 0, "Connecting to Zep graph...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "Reading node data...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"Completed, total {filtered.filtered_count} entities",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0 and not enable_synthetic_delegates:
                state.status = SimulationStatus.FAILED
                state.error = "No matching entities found. Please check whether the graph was built correctly"
                self._save_simulation_state(state)
                return state

            # ========== Stage 1.5: Synthetic delegate generation ==========
            if enable_synthetic_delegates:
                if progress_callback:
                    progress_callback(
                        "generating_delegates", 0,
                        "Inferring 3GPP delegate distribution...",
                        current=0, total=synthetic_delegate_count
                    )
                delegate_gen = SyntheticDelegateGenerator()
                distribution = delegate_gen.infer_distribution(
                    document_text=document_text,
                    simulation_requirement=simulation_requirement,
                    total_delegates=synthetic_delegate_count,
                    manual_config=synthetic_delegate_config,
                )

                def delegate_progress(current, total, msg):
                    if progress_callback:
                        progress_callback(
                            "generating_delegates",
                            int(current / max(total, 1) * 100),
                            msg,
                            current=current, total=total
                        )

                synthetic_nodes, synthetic_profiles = delegate_gen.generate(
                    distribution=distribution,
                    document_text=document_text,
                    simulation_requirement=simulation_requirement,
                    progress_callback=delegate_progress,
                )
                logger.info(
                    f"Synthetic delegate generation complete: {len(synthetic_nodes)} delegates"
                )
                if progress_callback:
                    progress_callback(
                        "generating_delegates", 100,
                        f"Generated {len(synthetic_nodes)} synthetic delegates",
                        current=len(synthetic_nodes), total=len(synthetic_nodes)
                    )
            
            # ========== Stage 2: Generate agent profiles ==========
            total_entities = len(filtered.entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0, 
                    "Starting generation...",
                    current=0,
                    total=total_entities
                )
            
            # Pass graph_id to enable Zep retrieval and obtain richer context
            generator = OasisProfileGenerator(graph_id=state.graph_id)
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # Set real-time output path (prefer Reddit JSON format)
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # Pass graph_id for Zep retrieval
                parallel_count=parallel_profile_count,  # Parallel generation count
                realtime_output_path=realtime_output_path,  # Real-time output path
                output_platform=realtime_platform  # Output format
            )

            if use_llm_for_profiles:
                log_llm_interaction(
                    source_file="simulation_manager.py",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"generate_profiles_from_entities: simulation_id={simulation_id}, "
                            f"graph_id={state.graph_id}, entity_count={len(filtered.entities)}, "
                            f"parallel_count={parallel_profile_count}"
                        ),
                    }],
                    response_text=f"generated_profiles_count={len(profiles)}",
                )
            
            # Merge synthetic profiles — must happen before save_profiles calls
            for i, sp in enumerate(synthetic_profiles):
                sp.user_id = len(profiles) + i
            profiles = profiles + synthetic_profiles
            state.profiles_count = len(profiles)

            # Save profile files (note: Twitter uses CSV format, Reddit uses JSON format)
            # Reddit has already been saved in real-time during generation; save again here to ensure completeness
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95, 
                    "Saving profile files...",
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # Twitter uses CSV format, required by OASIS
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100, 
                    f"Completed, total {len(profiles)} profiles",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== Stage 3: LLM-based intelligent simulation config generation ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "Analyzing simulation requirements...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "Calling LLM to generate configuration...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities + synthetic_nodes,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )

            log_llm_interaction(
                source_file="simulation_manager.py",
                messages=[{
                    "role": "user",
                    "content": (
                        f"generate_simulation_config: simulation_id={simulation_id}, "
                        f"project_id={state.project_id}, graph_id={state.graph_id}, "
                        f"requirement={simulation_requirement}"
                    ),
                }],
                response_text=(sim_params.generation_reasoning or "simulation_config_generated"),
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "Saving configuration file...",
                    current=2,
                    total=3
                )
            
            # Save configuration file
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "Configuration generation completed",
                    current=3,
                    total=3
                )
            
            # Note: Runtime scripts remain in `backend/scripts/` and are no longer copied to simulation directory
            # When starting simulation, `simulation_runner` runs scripts from the `scripts/` directory
            
            # Update status
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Simulation preparation completed: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"Simulation preparation failed: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def check_prepared(self, simulation_id: str) -> tuple:
        """
        Check if simulation preparation is complete.
        
        Returns:
            (is_prepared: bool, info: dict)
        """
        sim_dir = self._get_simulation_dir(simulation_id)
        
        if not os.path.exists(sim_dir):
            return False, {"reason": "Simulation directory does not exist"}
        
        required_files = ["state.json", "simulation_config.json", "reddit_profiles.json", "twitter_profiles.csv"]
        existing_files = []
        missing_files = []
        for f in required_files:
            if os.path.exists(os.path.join(sim_dir, f)):
                existing_files.append(f)
            else:
                missing_files.append(f)
        
        if missing_files:
            return False, {"reason": "Missing necessary files", "missing_files": missing_files, "existing_files": existing_files}
        
        state_file = os.path.join(sim_dir, "state.json")
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            status = state_data.get("status", "")
            config_generated = state_data.get("config_generated", False)
            
            prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
            if status in prepared_statuses and config_generated:
                profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
                profiles_count = 0
                if os.path.exists(profiles_file):
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles_data = json.load(f)
                        profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
                
                # Auto-fix preparing -> ready
                if status == "preparing":
                    try:
                        state_data["status"] = "ready"
                        state_data["updated_at"] = datetime.now().isoformat()
                        with open(state_file, 'w', encoding='utf-8') as f:
                            json.dump(state_data, f, ensure_ascii=False, indent=2)
                        status = "ready"
                    except Exception:
                        pass
                
                return True, {
                    "status": status,
                    "entities_count": state_data.get("entities_count", 0),
                    "profiles_count": profiles_count,
                    "entity_types": state_data.get("entity_types", []),
                    "config_generated": config_generated,
                    "created_at": state_data.get("created_at"),
                    "updated_at": state_data.get("updated_at"),
                    "existing_files": existing_files
                }
            else:
                return False, {
                    "reason": f"status={status}, config_generated={config_generated}",
                    "status": status,
                    "config_generated": config_generated
                }
        except Exception as e:
            return False, {"reason": f"Failed to read state file: {str(e)}"}

    def run_prepare_task(
        self,
        task_id: str,
        task_manager,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        entity_types_list: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        parallel_profile_count: int = 5,
        enable_synthetic_delegates: bool = True,
        synthetic_delegate_count: int = 30,
        synthetic_delegate_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Run the prepare task with progress reporting via TaskManager.
        Designed to be called from a background thread.
        """
        from ..models.task import TaskStatus
        
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Starting to prepare simulation environment...")
            
            stage_weights = {
                "reading": (0, 15),
                "generating_delegates": (15, 40),
                "generating_profiles": (40, 70),
                "generating_config": (70, 90),
                "copying_scripts": (90, 100)
            }
            stage_names = {
                "reading": "Reading graph entities",
                "generating_delegates": "Generating synthetic delegates",
                "generating_profiles": "Generating Agent personas",
                "generating_config": "Generating simulation config",
                "copying_scripts": "Preparing simulation scripts"
            }
            
            def progress_callback(stage, progress, message, **kwargs):
                start, end = stage_weights.get(stage, (0, 100))
                current_progress = int(start + (end - start) * progress / 100)
                stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                total_stages = len(stage_weights)
                
                current = kwargs.get("current", 0)
                total = kwargs.get("total", 0)
                
                progress_detail = {
                    "current_stage": stage,
                    "current_stage_name": stage_names.get(stage, stage),
                    "stage_index": stage_index,
                    "total_stages": total_stages,
                    "stage_progress": progress,
                    "current_item": current,
                    "total_items": total,
                    "item_description": message
                }
                
                if total > 0:
                    detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {current}/{total} - {message}"
                else:
                    detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                
                task_manager.update_task(task_id, progress=current_progress, message=detailed_message, progress_detail=progress_detail)
            
            result_state = self.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                defined_entity_types=entity_types_list,
                use_llm_for_profiles=use_llm_for_profiles,
                progress_callback=progress_callback,
                parallel_profile_count=parallel_profile_count,
                enable_synthetic_delegates=enable_synthetic_delegates,
                synthetic_delegate_count=synthetic_delegate_count,
                synthetic_delegate_config=synthetic_delegate_config,
            )
            
            task_manager.complete_task(task_id, result=result_state.to_simple_dict())
            
        except Exception as e:
            logger.error(f"Failed to prepare simulation: {str(e)}")
            task_manager.fail_task(task_id, str(e))
            
            state = self.get_simulation(simulation_id)
            if state:
                state.status = SimulationStatus.FAILED
                state.error = str(e)
                self._save_simulation_state(state)

    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Get simulation state."""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """List all simulations."""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Skip hidden files (e.g., .DS_Store) and non-directory files
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """Get simulation agent profiles."""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation configuration."""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Get run instructions."""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Activate conda environment: conda activate MiroFish\n"
                f"2. Run simulation (scripts are in {scripts_dir}):\n"
                f"   - Run Twitter only: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Run Reddit only: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Run both platforms in parallel: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
