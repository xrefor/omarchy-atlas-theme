"""Ports & Services panel using the shared tmux lifecycle and sidebar sizing."""
from atlas_panel_tmux import Panel as BasePanel


class Panel(BasePanel):
    name = 'atlas-ports'
    window_name = 'ports-services'
    owner_option = '@atlas_ports_origin'
