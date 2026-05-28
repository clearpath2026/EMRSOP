from typing import Optional, Tuple, Dict, List


class EMRDetector:
    def __init__(
        self,
        emr_modules: Dict[str, Dict[str, List[str]]],
        emr_processes: Dict[str, Dict],
    ):
        self._modules = emr_modules
        self._processes = emr_processes

    def detect(
        self, window_title: str, process_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        title_lower = window_title.lower()
        process_lower = process_name.lower()

        for emr, proc_cfg in self._processes.items():
            process_match = any(
                p.lower() == process_lower for p in proc_cfg["process_names"]
            )
            title_match = any(
                pat.lower() in title_lower
                for pat in proc_cfg["window_title_patterns"]
            )
            if not (process_match and title_match):
                continue

            for module, keywords in self._modules.get(emr, {}).items():
                if any(kw.lower() in title_lower for kw in keywords):
                    return emr, module

            return emr, "unknown_module"

        return None, None
