class EPaperDisplay:
    """Waveshare 7.5" v2 e-ink -ajuri (vain Raspberry Pi)."""

    def show(self, image, **kwargs):
        try:
            from waveshare_epd import epd7in5_V2
        except ImportError:
            raise RuntimeError(
                "waveshare_epd ei ole asennettu. Aja: pip install waveshare-epd "
                "tai kloonaa https://github.com/waveshare/e-Paper"
            )

        epd = epd7in5_V2.EPD()
        epd.init()
        epd.display(epd.getbuffer(image.convert("1")))  # 1-bittinen
        epd.sleep()  # Tärkeää – säästää näytön elinkaarta
