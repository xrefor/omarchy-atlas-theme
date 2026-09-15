/* Omarchy palette: appearance only; keep GTK widget geometry and behavior. */
@define-color theme_fg_color {{ foreground }};
@define-color theme_text_color {{ foreground }};
@define-color theme_bg_color {{ background }};
@define-color theme_base_color {{ dark_background }};
@define-color theme_selected_bg_color {{ accent }};
@define-color theme_selected_fg_color {{ selection_foreground }};
@define-color theme_unfocused_fg_color {{ light_foreground }};
@define-color theme_unfocused_text_color {{ light_foreground }};
@define-color theme_unfocused_bg_color {{ background }};
@define-color theme_unfocused_base_color {{ dark_background }};
@define-color theme_unfocused_selected_bg_color {{ selection }};
@define-color theme_unfocused_selected_fg_color {{ foreground }};
@define-color insensitive_bg_color {{ lighter_background }};
@define-color insensitive_fg_color mix({{ foreground }}, {{ background }}, 0.4);
@define-color insensitive_base_color {{ background }};
@define-color borders {{ muted }};
@define-color unfocused_borders {{ muted }};
@define-color content_view_bg {{ dark_background }};
@define-color text_view_bg {{ dark_background }};

/* Adwaita 3 uses literal colors in many rules, so named colors alone
 * cannot recolor its primary surfaces. Preserve its semantic action colors. */
.background, .background:backdrop {
  background-color: @theme_bg_color;
  color: @theme_fg_color;
}
headerbar, headerbar:backdrop, toolbar, menubar {
  background-image: none;
  background-color: {{ lighter_background }};
  color: @theme_fg_color;
  border-color: @borders;
}
.view, .view:backdrop, textview text, treeview.view, list, flowbox {
  background-color: @theme_base_color;
  color: @theme_text_color;
}
entry, entry:backdrop, spinbutton:not(.vertical) {
  background-color: {{ lighter_background }};
  color: @theme_text_color;
  border-color: @borders;
}
entry:focus, spinbutton:focus, button:focus {
  border-color: @theme_selected_bg_color;
}
popover, menu, tooltip {
  background-color: {{ lighter_background }};
  color: @theme_fg_color;
  border-color: @borders;
}
button:not(.suggested-action):not(.destructive-action):not(.flat):not(:disabled) {
  background-image: none;
  background-color: {{ lighter_background }};
  color: @theme_fg_color;
  border-color: @borders;
}
button:not(.suggested-action):not(.destructive-action):hover:not(:disabled) {
  background-image: none;
  background-color: {{ selection }};
}
button:not(.suggested-action):not(.destructive-action):checked:not(:disabled),
button:not(.suggested-action):not(.destructive-action):active:not(:disabled) {
  background-image: none;
  background-color: {{ selection }};
  border-color: {{ accent }};
}
button.suggested-action:not(:disabled), button.suggested-action:hover:not(:disabled),
switch:checked:not(:disabled), check:checked:not(:disabled), radio:checked:not(:disabled),
progressbar progress, scale highlight {
  background-image: none;
  background-color: @theme_selected_bg_color;
  color: @theme_selected_fg_color;
  border-color: @theme_selected_bg_color;
}
selection, .view:selected, .view:selected:focus,
row:selected, row:selected:focus, menuitem:hover {
  background-color: @theme_selected_bg_color;
  color: @theme_selected_fg_color;
}
button:disabled, entry:disabled, .view:disabled {
  color: @insensitive_fg_color;
}
/* Match the normal-button selector specificity so keyboard focus survives. */
button:not(.suggested-action):not(.destructive-action):not(.flat):not(:disabled):focus {
  border-color: @theme_selected_bg_color;
}
