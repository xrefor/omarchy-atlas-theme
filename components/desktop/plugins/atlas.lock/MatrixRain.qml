import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "MatrixModel.js" as Matrix

Item {
  id: root

  property bool running: visible
  property int glyphSize: 18
  property string brandText: ""
  readonly property string paletteKey: [Color.background, Color.foreground, Color.muted, Color.accent, Color.lock.placeholder, Style.font.family].join("|")

  readonly property string brandPath: Quickshell.env("HOME") + "/.config/omarchy/branding/screensaver.txt"

  property var sim: null

  function cellWidth() {
    return Math.max(1, Math.round(cellMetrics.advanceWidth))
  }

  function cellHeight() {
    return Math.max(root.glyphSize, Math.round(cellMetrics.height))
  }

  function rebuild() {
    if (width <= 0 || height <= 0) return
    var cw = cellWidth()
    var ch = cellHeight()
    Matrix.setAppearance(String(Color.background), String(Color.foreground), String(Color.muted), String(Color.accent), String(Color.lock.placeholder), Style.font.family)
    root.sim = Matrix.create(Math.floor(width / cw), Math.floor(height / ch), root.brandText, cw, ch, root.glyphSize)
    canvas.requestPaint()
  }

  onWidthChanged: Qt.callLater(rebuild)
  onHeightChanged: Qt.callLater(rebuild)
  onVisibleChanged: if (visible) Qt.callLater(rebuild)
  onRunningChanged: if (running) Qt.callLater(rebuild)
  onBrandTextChanged: if (visible) Qt.callLater(rebuild)
  onPaletteKeyChanged: if (visible) Qt.callLater(rebuild)
  Component.onCompleted: Qt.callLater(rebuild)

  FileView {
    path: root.brandPath
    watchChanges: true
    printErrors: false
    onLoaded: root.brandText = text()
    onFileChanged: reload()
  }

  TextMetrics {
    id: cellMetrics
    font.family: Style.font.family
    font.pixelSize: root.glyphSize
    text: "M"
  }

  Rectangle {
    anchors.fill: parent
    color: Color.background
  }

  Canvas {
    id: canvas
    anchors.fill: parent
    renderTarget: Canvas.FramebufferObject
    renderStrategy: Canvas.Cooperative
    antialiasing: false

    onPaint: {
      var ctx = getContext("2d")
      if (!ctx) return
      Matrix.paint(ctx, root.sim, width, height)
    }
  }

  Timer {
    interval: 16
    running: root.running && root.visible && root.width > 0 && root.sim !== null
    repeat: true
    onTriggered: {
      if (!Matrix.tick(root.sim)) root.rebuild()
      canvas.requestPaint()
    }
  }
}
