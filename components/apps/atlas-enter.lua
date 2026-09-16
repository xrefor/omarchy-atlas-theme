--- @since 25.5.31
--- @sync entry

-- Enter directories within Yazi; preserve the normal opener for files,
-- including its existing multi-selection behavior.
return {
  entry = function()
    local hovered = cx.active.current.hovered
    if not hovered then return end
    if hovered.cha.is_dir then
      ya.emit("enter", {})
    else
      ya.emit("open", {})
    end
  end,
}
