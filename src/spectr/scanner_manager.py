from .scanners import load_scanner, list_scanners
from .services import ScannerService
from . import cache


class ScannerManager:
    def __init__(self, data_api, exit_event):
        self.available_scanners = list_scanners()
        saved_scanner = cache.load_selected_scanner()
        default_scanner = saved_scanner or "CustomScanner"
        if default_scanner in self.available_scanners:
            self.scanner_name = default_scanner
        else:
            self.scanner_name = next(iter(self.available_scanners))
        self.scanner_class = load_scanner(self.scanner_name)
        cache.save_selected_scanner(self.scanner_name)

        self.scanner = self.scanner_class(data_api, exit_event)
        self._scanner_service = ScannerService(
            exit_event=exit_event,
            scanner=self.scanner,
            interval=config.SCANNER_INTERVAL,
            logger=log,
        )

    @property
    def scanner_results(self):
        return self.scanner.scanner_results

    @property
    def top_gainers(self):
        return self.scanner.top_gainers

    def start(self):
        self._scanner_service.start()

    def stop(self):
        self._scanner_service.stop()

    def cleanup(self):
        try:
            log.debug("stopping scanner service")
            self._scanner_service.stop()
        except Exception as e:
            log.warning(f"Error stopping scanner service: {e}")

    def __del__(self):
        self.cleanup()
