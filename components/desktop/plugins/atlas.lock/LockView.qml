import QtQuick
import QtQuick.Effects
import Quickshell.Io
import qs.Commons
import qs.Ui

Item {
  id: root

  property string backgroundPath: ""
  property int backgroundVersion: 0
  property bool fingerprintConfigured: false
  property bool authenticatingPassword: false
  property string failureMessage: ""
  property int failedAttempts: 0
  property bool inputEnabled: true
  property bool loadBackground: true
  property bool screensaverActive: false
  property string passwordText: ""
  property bool syncingPasswordText: false
  property bool capsLockOn: false

  readonly property string placeholderText: "Enter Password"
  readonly property int fieldWidth: 381
  readonly property int fieldHeight: 67
  // Keep two physical pixels at fractional scale so every edge stays visible.
  readonly property real dpr: Math.max(1, Screen.devicePixelRatio)
  readonly property real outlineThickness: Math.min(2, 2 / root.dpr)
  function snap(v) {
    return Math.round(Number(v) * root.dpr) / root.dpr
  }
  readonly property int fieldFontSize: Math.round(Style.font.heading * 1.125)
  readonly property int passwordDotFontSize: Math.round(Style.font.heading * 1.33)
  readonly property int passwordDotLetterSpacing: Math.round(Style.font.heading * 0.19)
  // Space to keep clear on each side of the field for the fingerprint icon
  // (icon width plus a gap) so the centered dots never run under it.
  readonly property real fingerprintReserve: fingerprintConfigured ? Math.round(fingerprintIcon.implicitWidth + 12) : 0
  readonly property real capsReserve: (capsLockOn && passwordText.length > 0) ? Style.space(40) : 0
  // Shrink the dots to fit once the password outgrows the field, so every
  // keystroke stays visible — otherwise long passwords clip with no feedback.
  readonly property real passwordDotScale: dotMetrics.advanceWidth > 0
    ? Math.min(1, (passwordInput.width - 4) / dotMetrics.advanceWidth)
    : 1
  readonly property bool showPasswordCursor: inputEnabled && !authenticatingPassword && failureMessage.length === 0
  readonly property bool errorState: failureMessage.length > 0
  readonly property var inputBorderSpec: errorState
    ? Border.surfaceSpec("lock", "border-error", Color.lock.borderError, root.outlineThickness, "border-alpha")
    : Border.surfaceSpec("lock", "border-active", Color.lock.borderActive, root.outlineThickness, "border-alpha")

  signal submitPassword(string password)
  signal passwordTextEdited(string password)
  signal clearFailureRequested()
  signal wakeRequested()
  signal screensaverDismissed()

  // Cache-busts the lock background by appending `?v=`. Adding a query
  // string keeps Image's loader happy while forcing it to reload when the
  // user picks a new background mid-session.
  function fileUrl(path) {
    if (!path) return ""
    var encoded = String(path).split("/").map(encodeURIComponent).join("/")
    return "file://" + encoded + "?v=" + backgroundVersion
  }

  function forcePasswordFocus() {
    passwordInput.forceActiveFocus()
  }

  function clearPassword() {
    passwordTextEdited("")
  }

  function syncPasswordText() {
    if (passwordInput.text === passwordText) return
    syncingPasswordText = true
    passwordInput.text = passwordText
    syncingPasswordText = false
  }

  onPasswordTextChanged: syncPasswordText()
  onInputEnabledChanged: {
    if (inputEnabled && !screensaverActive) Qt.callLater(forcePasswordFocus)
  }
  onScreensaverActiveChanged: {
    if (screensaverActive) Qt.callLater(function() { screensaverCatcher.forceActiveFocus() })
    else if (inputEnabled) Qt.callLater(forcePasswordFocus)
  }
  function refreshCapsLock() {
    if (!capsLockProc.running) capsLockProc.running = true
  }

  Component.onCompleted: {
    syncPasswordText()
    refreshCapsLock()
    if (inputEnabled && !screensaverActive) Qt.callLater(forcePasswordFocus)
  }

  // Measures the masked password at full size; passwordDotScale compares this
  // against the field width to decide how far the dots must shrink to fit.
  Process {
    id: capsLockProc
    command: ["bash", "-c", "for f in /sys/class/leds/*::capslock/brightness; do [ -r \"$f\" ] || continue; [ \"$(cat \"$f\")\" = 1 ] && echo on && exit 0; done; echo off"]
    stdout: StdioCollector { id: capsLockOut; waitForEnd: true }
    onExited: root.capsLockOn = String(capsLockOut.text || "").trim() === "on"
  }

  Timer {
    interval: 400
    running: true
    repeat: true
    onTriggered: root.refreshCapsLock()
  }

  TextMetrics {
    id: dotMetrics
    font.family: Style.font.family
    font.pixelSize: root.passwordDotFontSize
    font.letterSpacing: root.passwordDotLetterSpacing
    text: "●".repeat(passwordInput.text.length)
  }

  Rectangle {
    anchors.fill: parent
    color: Color.background

    Image {
      id: wallpaper
      anchors.fill: parent
      visible: !root.screensaverActive
      source: root.loadBackground ? root.fileUrl(root.backgroundPath) : ""
      fillMode: Image.PreserveAspectCrop
      asynchronous: true
      cache: false
      sourceSize.width: width
      sourceSize.height: height
    }

    MultiEffect {
      anchors.fill: wallpaper
      visible: !root.screensaverActive
      source: wallpaper
      autoPaddingEnabled: false
      blurEnabled: root.loadBackground && wallpaper.status === Image.Ready
      blur: 1.0
      blurMax: 128
      blurMultiplier: 1.25
      contrast: -0.08
    }

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      enabled: !root.screensaverActive
      onClicked: { root.wakeRequested(); root.forcePasswordFocus() }
      onPositionChanged: root.wakeRequested()
    }

    MatrixRain {
      anchors.fill: parent
      visible: root.screensaverActive
      running: visible
      z: 10
    }

    Item {
      id: screensaverCatcher
      anchors.fill: parent
      visible: root.screensaverActive
      focus: root.screensaverActive
      z: 20
      property real lastMouseX: -1
      property real lastMouseY: -1

      onVisibleChanged: {
        lastMouseX = -1
        lastMouseY = -1
        if (visible) Qt.callLater(function() { screensaverCatcher.forceActiveFocus() })
      }

      Keys.onPressed: function(event) {
        event.accepted = true
        root.screensaverDismissed()
      }

      MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.BlankCursor
        acceptedButtons: Qt.AllButtons
        onPressed: function(mouse) {
          mouse.accepted = true
          root.screensaverDismissed()
        }
        onPositionChanged: function(mouse) {
          if (screensaverCatcher.lastMouseX < 0) {
            screensaverCatcher.lastMouseX = mouse.x
            screensaverCatcher.lastMouseY = mouse.y
            return
          }
          if (Math.abs(mouse.x - screensaverCatcher.lastMouseX) + Math.abs(mouse.y - screensaverCatcher.lastMouseY) < 8)
            return
          root.screensaverDismissed()
        }
      }
    }

    // SDDM-style centered tile: padlock beside a framed password field.
    // Pixel-align the row. A 1px border on a half-pixel Y (odd field height
    // centered on an even screen) loses its top hairline; clip on the frame
    // then eats that same pixel.
    Row {
      id: promptRow
      visible: !root.screensaverActive
      x: root.snap((parent.width - width) / 2)
      y: root.snap((parent.height - height) / 2)
      spacing: 15

      Text {
        text: "\uf023"
        color: root.errorState ? Color.lock.textError : Color.lock.text
        font.family: Style.font.family
        font.pixelSize: Math.round(root.fieldFontSize * 1.7)
        width: Math.round(root.fieldHeight * 0.7)
        height: inputField.height
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
      }

      BorderSurface {
        id: inputField
        width: root.snap(root.fieldWidth)
        height: root.snap(root.fieldHeight)
        color: Color.lock.background
        borderSpec: root.inputBorderSpec
        border.pixelAligned: false
        radius: Style.cornerRadius
        antialiasing: false

      Item {
        id: fieldClip
        anchors.fill: parent
        anchors.topMargin: inputField.borderTop
        anchors.rightMargin: inputField.borderRight
        anchors.bottomMargin: inputField.borderBottom
        anchors.leftMargin: inputField.borderLeft
        clip: true

      TextInput {
        id: passwordInput
        anchors.fill: parent
        // Reserve the fingerprint icon's width on both sides so the centered
        // dots stay symmetric and never slide under the icon as they grow.
        anchors.rightMargin: 18 + root.fingerprintReserve + root.capsReserve
        anchors.leftMargin: 18 + root.fingerprintReserve + root.capsReserve
        verticalAlignment: TextInput.AlignVCenter
        horizontalAlignment: TextInput.AlignHCenter
        activeFocusOnPress: true
        clip: true
        enabled: root.inputEnabled && !root.authenticatingPassword && !root.screensaverActive
        readOnly: root.authenticatingPassword
        echoMode: TextInput.Password
        passwordCharacter: "\u25CF"
        passwordMaskDelay: 0
        color: Color.lock.text
        selectionColor: Color.lock.selection
        selectedTextColor: Color.lock.text
        font.family: Style.font.family
        font.pixelSize: text.length > 0 ? Math.max(1, Math.floor(root.passwordDotFontSize * root.passwordDotScale)) : root.fieldFontSize
        font.letterSpacing: text.length > 0 ? root.passwordDotLetterSpacing * root.passwordDotScale : 0
        cursorVisible: activeFocus && root.showPasswordCursor && text.length > 0
        cursorDelegate: Rectangle {
          width: 2
          color: Color.lock.text
          visible: passwordInput.cursorVisible
        }

        onTextChanged: {
          if (!root.syncingPasswordText) root.passwordTextEdited(text)
          if (text.length > 0) {
            root.wakeRequested()
          }
          if (text.length > 0 && root.failureMessage.length > 0) root.clearFailureRequested()
        }

        onAccepted: {
          var submitted = root.passwordText
          root.passwordTextEdited("")
          if (submitted.length > 0) root.submitPassword(submitted)
        }

        Keys.onPressed: function(event) {
          root.wakeRequested()
          if (event.key === Qt.Key_CapsLock) Qt.callLater(root.refreshCapsLock)
          if (event.key === Qt.Key_Escape || (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_U)) {
            root.passwordTextEdited("")
            event.accepted = true
          }
        }
      }

      Text {
        anchors.fill: passwordInput
        text: root.authenticatingPassword ? "Checking…" : (root.failureMessage.length > 0 ? root.failureMessage : (root.capsLockOn ? "Caps Lock" : root.placeholderText))
        visible: passwordInput.text.length === 0
        color: root.authenticatingPassword ? Color.lock.text : (root.failureMessage.length > 0 ? Color.lock.textError : (root.capsLockOn ? Color.lock.borderActive : Color.lock.placeholder))
        font.family: Style.font.family
        font.pixelSize: root.fieldFontSize
        font.italic: !root.authenticatingPassword && root.failureMessage.length > 0
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
      }

      // Fingerprint hint pinned inside the field's right edge when a sensor is
      // enrolled, so the user knows they can touch to unlock instead of typing.
      // Matches hyprlock, which draws its fingerprint icon in the same spot.
      Text {
        id: fingerprintIcon
        objectName: "fingerprintIndicator"
        anchors.right: parent.right
        anchors.rightMargin: 18
        anchors.verticalCenter: parent.verticalCenter
        visible: root.fingerprintConfigured
        text: "󰈷"
        color: Color.lock.placeholder
        font.family: Style.font.family
        font.pixelSize: Math.round(root.fieldFontSize * 1.1)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
      }

      Text {
        visible: root.capsLockOn && passwordInput.text.length > 0 && !root.authenticatingPassword && root.failureMessage.length === 0
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.verticalCenter: parent.verticalCenter
        text: "CAPS"
        color: Color.lock.borderActive
        font.family: Style.font.family
        font.pixelSize: Math.round(root.fieldFontSize * 0.55)
        font.bold: true
      }
      }
      }
    }
  }
}
