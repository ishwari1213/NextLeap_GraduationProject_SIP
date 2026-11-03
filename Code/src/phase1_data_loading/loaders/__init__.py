"""One loader per source type in Data/sources/sources.yaml (architecture phase 1)."""
from src.phase1_data_loading.loaders import (
    app_store,
    discourse,
    info_pages,
    play_store,
    reddit,
    team_bhp,
    youtube,
)

LOADERS = {
    module.SOURCE: module
    for module in (play_store, app_store, discourse, reddit, team_bhp, youtube, info_pages)
}
