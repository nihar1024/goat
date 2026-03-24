from goatlib.config.base import BaseSettingsModel


class PrintSettings(BaseSettingsModel):
    """Settings for report printing / atlas rendering."""

    atlas_batch_size: int = 2  # Parallel atlas pages per batch (1 per CPU core recommended)
