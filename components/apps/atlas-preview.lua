--- @since 26.8.15
--- @sync entry

-- Keep a narrow file list while reading a larger preview. Runtime-only: the
-- next Yazi session starts with the configured browsing layout.
return {
  entry = function(self)
    local ratio = rt.mgr.ratio
    local expanded = ratio[1] == 0 and ratio[2] == 1 and ratio[3] == 7
    if expanded then
      rt.mgr.ratio = self.previous or { 1, 4, 3 }
      self.previous = nil
    else
      self.previous = { ratio[1], ratio[2], ratio[3] }
      rt.mgr.ratio = { 0, 1, 7 }
    end
    ya.emit("app:resize", {})
  end,
}
