"""Git Status panel using the shared tmux lifecycle and sidebar sizing."""
from atlas_panel_tmux import Panel as BasePanel


class Panel(BasePanel):
    name = 'atlas-projects'
    window_name = 'git-status'
    owner_option = '@atlas_projects_origin'

    def command_for_origin(self):
        current_path = self._tmux('display-message', '-p', '-t', self.origin,
                                  '#{pane_current_path}')
        if not current_path or '\0' in current_path:
            raise ValueError('The originating tmux pane has no usable current path')
        return [*self.command, '--path', current_path]
