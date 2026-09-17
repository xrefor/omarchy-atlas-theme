import QtQuick
import QtQuick.Effects
import Quickshell.Io
import qs.Commons
import qs.Ui

Item {
  id: root

  property bool terminalStyle: false
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
  // Window visibility is separate from Item.visible; the owner supplies it.
  property bool surfaceActive: false
  readonly property bool capsLockPolling: surfaceActive && visible && !screensaverActive

  readonly property string placeholderText: terminalStyle ? "" : "Enter Password"
  readonly property int fieldWidth: terminalStyle ? 220 : 381
  readonly property int fieldHeight: terminalStyle ? 38 : 67
  // Keep two physical pixels at fractional scale so every edge stays visible.
  readonly property real dpr: Math.max(1, Screen.devicePixelRatio)
  readonly property real outlineThickness: Math.min(2, 2 / root.dpr)
  function snap(v) {
    return Math.round(Number(v) * root.dpr) / root.dpr
  }
  readonly property int fieldFontSize: terminalStyle ? terminalTypography.fontInfo.pixelSize : Math.round(Style.font.heading * 1.125)
  readonly property int passwordDotFontSize: terminalStyle ? terminalTypography.fontInfo.pixelSize : Math.round(Style.font.heading * 1.33)
  readonly property int passwordDotLetterSpacing: terminalStyle ? 2 : Math.round(Style.font.heading * 0.19)
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
    if (capsLockPolling && !capsLockProc.running) capsLockProc.running = true
  }

  Component.onCompleted: {
    syncPasswordText()
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
    running: root.capsLockPolling
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refreshCapsLock()
  }

  Text {
    id: terminalTypography
    visible: false
    font.family: "IBM Plex Mono"
    font.pointSize: 9
  }

  TextMetrics {
    id: dotMetrics
    font.family: root.terminalStyle ? "IBM Plex Mono" : Style.font.family
    font.pixelSize: root.passwordDotFontSize
    font.letterSpacing: root.passwordDotLetterSpacing
    text: passwordInput.passwordCharacter.repeat(passwordInput.text.length)
  }

  Rectangle {
    anchors.fill: parent
    color: root.terminalStyle ? "#100e0c" : Color.background

    Image {
      id: wallpaper
      anchors.fill: parent
      visible: !root.screensaverActive && !root.terminalStyle
      source: root.loadBackground && !root.terminalStyle ? root.fileUrl(root.backgroundPath) : ""
      fillMode: Image.PreserveAspectCrop
      asynchronous: true
      cache: false
      sourceSize.width: width
      sourceSize.height: height
    }

    MultiEffect {
      anchors.fill: wallpaper
      visible: !root.screensaverActive && !root.terminalStyle
      source: wallpaper
      autoPaddingEnabled: false
      blurEnabled: !root.terminalStyle && root.loadBackground && wallpaper.status === Image.Ready
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

    Image {
      id: atlasLogo
      visible: root.terminalStyle && !root.screensaverActive
      source: Qt.resolvedUrl("atlas.svg")
      width: 280
      height: 56
      anchors.horizontalCenter: parent.horizontalCenter
      y: root.snap((parent.height - height - 24 - root.fieldHeight) / 2)
      fillMode: Image.PreserveAspectFit
      smooth: true
    }

    // SDDM-style centered tile: padlock beside a framed password field.
    // Pixel-align the row. A 1px border on a half-pixel Y (odd field height
    // centered on an even screen) loses its top hairline; clip on the frame
    // then eats that same pixel.
    Row {
      id: promptRow
      visible: !root.screensaverActive
      x: root.snap((parent.width - width) / 2)
      y: root.terminalStyle ? root.snap(atlasLogo.y + atlasLogo.height + 24) : root.snap((parent.height - height) / 2)
      spacing: 15

      Text {
        visible: !root.terminalStyle
        text: "\uf023"
        color: root.errorState ? Color.lock.textError : Color.lock.text
        font.family: root.terminalStyle ? "IBM Plex Mono" : Style.font.family
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
        color: root.terminalStyle ? "transparent" : Color.lock.background
        borderSpec: root.terminalStyle ? Border.none() : root.inputBorderSpec
        border.pixelAligned: false
        radius: root.terminalStyle ? 0 : Style.cornerRadius
        antialiasing: false

      Item {
        id: fieldClip
        anchors.fill: parent
        anchors.topMargin: inputField.borderTop
        anchors.rightMargin: inputField.borderRight
        anchors.bottomMargin: inputField.borderBottom
        anchors.leftMargin: inputField.borderLeft
        clip: true

      Text {
        id: terminalPrompt
        visible: root.terminalStyle
        text: ">"
        anchors.left: parent.left
        anchors.leftMargin: 13
        anchors.verticalCenter: parent.verticalCenter
        color: root.errorState ? Color.lock.textError : "#a69b8c"
        font.family: "IBM Plex Mono"
        font.pointSize: 9

        SequentialAnimation on opacity {
          running: root.terminalStyle && !root.screensaverActive && !root.authenticatingPassword && !root.errorState
          loops: Animation.Infinite
          onStopped: terminalPrompt.opacity = 1
          PauseAnimation { duration: 500 }
          NumberAnimation { to: 0; duration: 100 }
          PauseAnimation { duration: 500 }
          NumberAnimation { to: 1; duration: 100 }
        }
      }

      TextInput {
        id: passwordInput
        anchors.fill: parent
        // Reserve the fingerprint icon's width on both sides so the centered
        // dots stay symmetric and never slide under the icon as they grow.
        anchors.rightMargin: 18 + root.fingerprintReserve + root.capsReserve
        anchors.leftMargin: root.terminalStyle ? 29 + root.capsReserve : 18 + root.fingerprintReserve + root.capsReserve
        verticalAlignment: TextInput.AlignVCenter
        horizontalAlignment: root.terminalStyle ? TextInput.AlignLeft : TextInput.AlignHCenter
        activeFocusOnPress: true
        clip: true
        enabled: root.inputEnabled && !root.authenticatingPassword && !root.screensaverActive
        readOnly: root.authenticatingPassword
        echoMode: TextInput.Password
        passwordCharacter: root.terminalStyle ? "*" : "\u25CF"
        passwordMaskDelay: 0
        color: Color.lock.text
        selectionColor: Color.lock.selection
        selectedTextColor: Color.lock.text
        font.family: root.terminalStyle ? "IBM Plex Mono" : Style.font.family
        font.pixelSize: text.length > 0 ? Math.max(1, Math.floor(root.passwordDotFontSize * root.passwordDotScale)) : root.fieldFontSize
        font.letterSpacing: text.length > 0 ? root.passwordDotLetterSpacing * root.passwordDotScale : 0
        cursorVisible: activeFocus && root.showPasswordCursor && (root.terminalStyle || text.length > 0)
        cursorDelegate: Rectangle {
          width: root.terminalStyle ? 1 / root.dpr : 2
          color: root.terminalStyle ? "#ff5a12" : Color.lock.text
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
        visible: passwordInput.text.length === 0 && !(root.terminalStyle && root.errorState && !root.authenticatingPassword)
        color: root.authenticatingPassword ? Color.lock.text : (root.failureMessage.length > 0 ? Color.lock.textError : (root.capsLockOn ? Color.lock.borderActive : Color.lock.placeholder))
        font.family: root.terminalStyle ? "IBM Plex Mono" : Style.font.family
        font.pixelSize: root.fieldFontSize
        font.italic: !root.authenticatingPassword && root.failureMessage.length > 0
        horizontalAlignment: root.terminalStyle ? Text.AlignLeft : Text.AlignHCenter
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
        anchors.leftMargin: root.terminalStyle ? 29 : 18
        anchors.verticalCenter: parent.verticalCenter
        text: "CAPS"
        color: Color.lock.borderActive
        font.family: root.terminalStyle ? "IBM Plex Mono" : Style.font.family
        font.pixelSize: root.terminalStyle ? root.fieldFontSize : Math.round(root.fieldFontSize * 0.55)
        font.bold: true
      }
      }
      }
    }

    // Native PAM messages can outgrow the narrow Terminal password prompt.
    // Keep the prompt steady and let the complete error wrap beneath it.
    Text {
      objectName: "terminalFailureMessage"
      visible: root.terminalStyle && !root.screensaverActive && !root.authenticatingPassword
        && root.passwordText.length === 0 && root.errorState
      anchors.horizontalCenter: parent.horizontalCenter
      y: root.snap(promptRow.y + promptRow.height + 8)
      width: root.snap(Math.max(0, Math.min(420, parent.width - 32)))
      text: root.failureMessage
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: Color.lock.textError
      font.family: "IBM Plex Mono"
      font.pixelSize: root.fieldFontSize
      font.italic: true
      horizontalAlignment: Text.AlignHCenter
    }
  }
}
