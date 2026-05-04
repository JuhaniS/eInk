import subprocess
from pathlib import Path


class SimulatorDisplay:
    """Mac-simulaatio: tallentaa kuvan PNG:nä ja avaa sen Preview-ohjelmalla."""

    OUTPUT_PATH = Path("output/dashboard.png")

    PARTIAL_PATH = Path("output/partial.png")

    def show(self, image, open_preview: bool = False):
        self.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.save(self.OUTPUT_PATH)
        print(f"Kuva tallennettu: {self.OUTPUT_PATH.resolve()}")

        if open_preview:
            subprocess.Popen(["open", str(self.OUTPUT_PATH)])

    show_full = show

    def show_partials(self, regions, open_preview: bool = False):
        """Simulator stand-in for multi-region partial refresh.

        Overlays each region onto `output/dashboard.png` (single open/save)
        and writes the last region to `output/partial.png` for inspection."""
        if not regions:
            return
        from PIL import Image
        self.PARTIAL_PATH.parent.mkdir(parents=True, exist_ok=True)

        regions[-1][0].save(self.PARTIAL_PATH)
        print(f"Partial region saved: {self.PARTIAL_PATH.resolve()} "
              f"(boxes={[box for _, box in regions]})")

        if self.OUTPUT_PATH.exists():
            full = Image.open(self.OUTPUT_PATH).convert("L")
            for region_image, box in regions:
                full.paste(region_image.convert("L"), (box[0], box[1]))
            full.save(self.OUTPUT_PATH)

        if open_preview:
            subprocess.Popen(["open", str(self.PARTIAL_PATH)])
