"""
Usage (run as Administrator):
  python install_service.py install
  python install_service.py start
  python install_service.py stop
  python install_service.py remove
"""
import sys
import win32serviceutil
from agent.service.main import EMRTrackerService


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "install":
        win32serviceutil.InstallService(
            pythonClassString="agent.service.main.EMRTrackerService",
            serviceName=EMRTrackerService._svc_name_,
            displayName=EMRTrackerService._svc_display_name_,
            description=EMRTrackerService._svc_description_,
            startType=win32serviceutil.win32service.SERVICE_AUTO_START,
        )
        print(f"Service '{EMRTrackerService._svc_name_}' installed.")
    elif command == "start":
        win32serviceutil.StartService(EMRTrackerService._svc_name_)
        print("Service started.")
    elif command == "stop":
        win32serviceutil.StopService(EMRTrackerService._svc_name_)
        print("Service stopped.")
    elif command == "remove":
        win32serviceutil.RemoveService(EMRTrackerService._svc_name_)
        print("Service removed.")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
