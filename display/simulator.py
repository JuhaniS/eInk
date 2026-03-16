import os
import subprocess
from pathlib import Path


class SimulatorDisplay:
    """Mac-simulaatio: tallentaa kuvan PNG:nä ja avaa sen Preview-ohjelmalla."""

    OUTPUT_PATH = Path("output/dashboard.png")

    def show(self, image, open_preview: bool = False):
        self.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.save(self.OUTPUT_PATH)
        print(f"Kuva tallennettu: {self.OUTPUT_PATH.resolve()}")

        if open_preview:
            subprocess.Popen(["open", str(self.OUTPUT_PATH)])
