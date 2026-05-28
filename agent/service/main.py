import sys
import win32event
import win32service
import win32serviceutil
import servicemanager

from agent.service.config import load_config
from agent.tracker.emr_detector import EMRDetector
from agent.tracker.uia_tracker import UIATracker
from agent.redaction.engine import RedactionEngine
from agent.session.aggregator import SessionAggregator
from agent.storage.db import Database
from agent.storage.audit_log import AuditLogger


class EMRTrackerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "EMRTrackerService"
    _svc_display_name_ = "EMR Workflow Tracker"
    _svc_description_ = (
        "Tracks EMR activity for workflow analytics. PHIPA-compliant — "
        "no raw PHI stored or transmitted."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._tracker: UIATracker | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._tracker:
            self._tracker.stop()
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._run()

    def _run(self):
        config = load_config()
        db = Database(config.db_path)
        audit = AuditLogger(config.audit_log_path)
        redaction = RedactionEngine()
        detector = EMRDetector(config.emr_modules, config.emr_processes)
        aggregator = SessionAggregator(
            agent_id=config.agent_id,
            redaction_engine=redaction,
            db=db,
            audit=audit,
            config=config,
        )
        self._tracker = UIATracker(
            emr_detector=detector,
            event_callback=aggregator.on_event,
            poll_interval=config.poll_interval,
            rdp_processes=config.rdp_processes,
            rdp_ocr_interval=config.rdp_ocr_interval,
        )
        self._tracker.start()
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
        aggregator.force_close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(EMRTrackerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(EMRTrackerService)
