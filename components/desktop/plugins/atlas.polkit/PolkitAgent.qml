import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Polkit
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "PolkitModel.js" as PolkitModel

Item {
  id: root

  property string fontFamily: Style.font.menuFamily
  // Bound to the central [polkit] section in shell.toml via Color.qml.
  property color accent: Color.polkit.accent
  property color background: Color.polkit.background
  property color foreground: Color.polkit.text
  property color border: Color.polkit.border
  property color borderError: Color.polkit.borderError
  property var fieldBorderSpec: Border.surfaceSpec("polkit", errorFlash ? "border-error" : "border", errorFlash ? borderError : border, Style.normalBorderWidth, "border-alpha")
  property color scrim: Color.polkit.scrim
  readonly property int cornerRadius: Style.cornerRadius
  property int contentMargin: Style.spacing.panelPadding
  // Match the lock-screen field so every GUI login tile shares one frame size.
  property int fieldHeight: 67
  readonly property int fieldWidth: 381

  property bool closing: false
  property bool submitted: false
  property string currentMessage: ""
  property string currentPrompt: ""
  property string currentSupplementary: ""
  property bool responseRequired: false
  property bool responseVisible: false
  property bool failed: false
  property bool errorFlash: false
  // pam_fprintd appears in the polkit PAM stack (a sensor is enrolled).
  property bool fingerprintConfigured: false
  // Lid shut right now — the reader is physically unreachable, so we fall back
  // to the password even when a sensor is enrolled. Refreshed per request.
  property bool laptopClosed: false
  property bool capsLockOn: false
  property int shakeOffset: 0

  readonly property bool dialogVisible: polkitAgent.isActive || closing
  // We show one method at a time. Fingerprint owns the dialog while PAM is
  // waiting on the reader (lid open, sensor enrolled); the moment PAM asks for
  // a password — including immediately when the lid is shut and the clamshell
  // gate skips pam_fprintd — we switch to the password field instead.
  readonly property bool fingerprintMode: fingerprintConfigured && !laptopClosed && dialogVisible && !responseRequired && !submitted && !errorFlash

  function authorizationLabel(message) {
    return PolkitModel.authorizationLabel(message)
  }

  function loadPamConfig(raw) {
    fingerprintConfigured = PolkitModel.fingerprintConfiguredFromPamConfig(raw)
  }

  function refreshLidState() {
    if (!laptopClosedProc.running) laptopClosedProc.running = true
  }

  function refreshCapsLock() {
    if (!capsLockProc.running) capsLockProc.running = true
  }

  function resetSnapshot() {
    currentMessage = ""
    currentPrompt = ""
    currentSupplementary = ""
    responseRequired = false
    responseVisible = false
    failed = false
    errorFlash = false
    submitted = false
    passwordInput.text = ""
  }

  function syncFromFlow() {
    var flow = polkitAgent.flow
    if (!flow) return

    currentMessage = String(flow.message || "Authentication is needed...")
    currentPrompt = String(flow.inputPrompt || "")
    currentSupplementary = String(flow.supplementaryMessage || "")
    responseRequired = !!flow.isResponseRequired
    responseVisible = !!flow.responseVisible
    failed = !!flow.failed

    if (responseRequired) submitted = false
  }

  function beginFlow() {
    closeTimer.stop()
    closing = false
    submitted = false
    passwordInput.text = ""
    refreshLidState()
    refreshCapsLock()
    syncFromFlow()
    Qt.callLater(refocus)
  }

  function refocus() {
    if (!dialogVisible) return
    // In fingerprint mode there is no field to type into — park focus on the
    // key catcher so Escape still cancels; otherwise focus the password field.
    if (fingerprintMode) keyCatcher.forceActiveFocus()
    else passwordInput.forceActiveFocus()
  }

  function submitResponse() {
    var flow = polkitAgent.flow
    if (!flow || !flow.isResponseRequired) return
    submitted = true
    errorFlash = false
    flow.submit(passwordInput.text)
    passwordInput.text = ""
    keyCatcher.forceActiveFocus()
  }

  function cancelRequest() {
    var flow = polkitAgent.flow
    passwordInput.text = ""
    submitted = false
    closing = true
    closeTimer.restart()
    if (flow) flow.cancelAuthenticationRequest()
  }

  function triggerFailureFeedback() {
    submitted = false
    errorFlash = true
    passwordInput.text = ""
    errorTimer.restart()
    shakeAnimation.restart()
    Qt.callLater(refocus)
  }

  Timer {
    id: closeTimer
    interval: 300
    repeat: false
    onTriggered: {
      closing = false
      resetSnapshot()
    }
  }

  Timer {
    id: errorTimer
    interval: 1200
    repeat: false
    onTriggered: root.errorFlash = false
  }

  SequentialAnimation {
    id: shakeAnimation
    NumberAnimation { target: root; property: "shakeOffset"; to: -8; duration: 35; easing.type: Easing.OutQuad }
    NumberAnimation { target: root; property: "shakeOffset"; to: 8; duration: 50; easing.type: Easing.InOutQuad }
    NumberAnimation { target: root; property: "shakeOffset"; to: 0; duration: 55; easing.type: Easing.OutQuad }
  }
  FileView {
    path: "/etc/pam.d/polkit-1"
    watchChanges: true
    printErrors: false
    onLoaded: root.loadPamConfig(text())
    onLoadFailed: root.fingerprintConfigured = false
    onFileChanged: reload()
  }

  Process {
    id: laptopClosedProc
    command: ["bash", "-c", "omarchy-hw-laptop-closed && echo closed || echo open"]
    stdout: StdioCollector { id: laptopClosedOut; waitForEnd: true }
    onExited: root.laptopClosed = String(laptopClosedOut.text || "").trim() === "closed"
  }

  Process {
    id: capsLockProc
    command: ["bash", "-c", "for f in /sys/class/leds/*::capslock/brightness; do [ -r \"$f\" ] || continue; [ \"$(cat \"$f\")\" = 1 ] && echo on && exit 0; done; echo off"]
    stdout: StdioCollector { id: capsLockOut; waitForEnd: true }
    onExited: root.capsLockOn = String(capsLockOut.text || "").trim() === "on"
  }

  Timer {
    interval: 400
    running: root.dialogVisible
    repeat: true
    onTriggered: root.refreshCapsLock()
  }

  PolkitAgent {
    id: polkitAgent
    path: "/org/omarchy/PolkitAgent"

    onAuthenticationRequestStarted: root.beginFlow()
    onIsActiveChanged: {
      if (isActive) root.syncFromFlow()
      else if (!root.closing) root.resetSnapshot()
    }
    onIsRegisteredChanged: {
      if (isRegistered) console.log("omarchy polkit agent registered")
      else console.warn("omarchy polkit agent is not registered; another agent may be running")
    }
  }

  Connections {
    target: polkitAgent.flow

    function onIsResponseRequiredChanged() {
      root.syncFromFlow()
      if (!polkitAgent.flow || !polkitAgent.flow.isResponseRequired) passwordInput.text = ""
      Qt.callLater(root.refocus)
    }

    function onInputPromptChanged() { root.syncFromFlow() }
    function onResponseVisibleChanged() { root.syncFromFlow() }
    function onSupplementaryMessageChanged() { root.syncFromFlow() }
    function onFailedChanged() { root.syncFromFlow() }

    function onAuthenticationFailed() {
      root.syncFromFlow()
      root.triggerFailureFeedback()
    }

    function onAuthenticationSucceeded() {
      root.closing = true
      closeTimer.restart()
    }

    function onAuthenticationRequestCancelled() {
      root.closing = true
      closeTimer.restart()
    }
  }

  PanelWindow {
    id: panel
    visible: root.dialogVisible
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-polkit"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.refocus()
    }

    Item {
      id: tile
      x: Math.round((parent.width - width) / 2) + root.shakeOffset
      y: Math.round((parent.height - height) / 2)
      width: promptRow.width
      height: promptRow.height

      MouseArea { anchors.fill: parent; onClicked: root.refocus() }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            root.cancelRequest()
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (root.responseRequired) root.submitResponse()
            event.accepted = true
          }
        }
      }

      Row {
        id: promptRow
        spacing: 15

        Text {
          visible: !root.fingerprintMode
          text: "\uf023"
          color: root.errorFlash ? Color.polkit.textError : root.accent
          font.family: root.fontFamily
          font.pixelSize: Math.round(Style.font.iconLarge * 1.7)
          width: Math.round(root.fieldHeight * 0.7)
          height: root.fieldHeight
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
        }

        BorderSurface {
          id: field
          width: root.fingerprintMode ? root.fieldHeight : root.fieldWidth
          height: root.fieldHeight
          radius: root.cornerRadius
          color: root.background
          borderSpec: root.fieldBorderSpec

          OpticalGlyph {
            anchors.centerIn: parent
            width: Math.round(root.fieldHeight * 0.55)
            height: width
            visible: root.fingerprintMode
            text: "\udb80\ude37"
            fontFamily: root.fontFamily
            fontSize: Math.round(root.fieldHeight * 0.55)
            color: root.errorFlash ? Color.polkit.textError : root.accent
          }

          Item {
            visible: !root.fingerprintMode
            anchors.fill: parent
            anchors.topMargin: field.borderTop
            anchors.rightMargin: field.borderRight
            anchors.bottomMargin: field.borderBottom
            anchors.leftMargin: field.borderLeft
            clip: true

          Item {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18

            TextInput {
              id: passwordInput
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.right: parent.right
              anchors.rightMargin: capsBadge.visible ? capsBadge.width + Style.space(8) : 0
              verticalAlignment: TextInput.AlignVCenter
              activeFocusOnPress: true
              clip: true
              selectionColor: Util.alpha(root.accent, 0.45)
              selectedTextColor: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.iconLarge
              echoMode: root.responseVisible ? TextInput.Normal : TextInput.Password
              passwordCharacter: "\u2022"
              color: root.errorFlash ? Color.polkit.textError : root.foreground
              cursorVisible: activeFocus && !root.submitted && !root.errorFlash
              readOnly: root.submitted || root.errorFlash
              enabled: root.dialogVisible
              onAccepted: root.submitResponse()
              Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                  root.cancelRequest()
                  event.accepted = true
                }
                if (event.key === Qt.Key_CapsLock)
                  Qt.callLater(root.refreshCapsLock)
              }
            }

            Text {
              id: capsBadge
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              visible: root.capsLockOn && passwordInput.text.length > 0 && !root.errorFlash && !root.submitted
              text: "CAPS"
              color: root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.errorFlash ? "Wrong" : (root.submitted ? "Checking..." : (root.capsLockOn ? "Caps Lock" : "Enter password"))
              color: root.errorFlash ? Color.polkit.textError : (root.capsLockOn ? root.accent : root.foreground)
              opacity: root.errorFlash || root.capsLockOn ? 1 : 0.36
              font.family: root.fontFamily
              font.pixelSize: Style.font.iconLarge
              elide: Text.ElideRight
              visible: passwordInput.text.length === 0
            }

            Rectangle {
              width: Math.max(1, Style.space(2))
              height: Style.space(24)
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              color: root.errorFlash ? Color.polkit.textError : root.foreground
              visible: passwordInput.visible && passwordInput.activeFocus && passwordInput.text.length === 0 && !root.submitted && !root.errorFlash
            }

            MouseArea {
              anchors.fill: parent
              acceptedButtons: Qt.LeftButton
              enabled: passwordInput.visible
              onClicked: passwordInput.forceActiveFocus()
            }
          }
          }
        }
      }
    }

    BorderSurface {
      width: Math.min(root.fieldWidth, panel.width - Style.gapsOut * 2)
      height: justificationText.implicitHeight + Style.space(16)
      // The field is nested in promptRow; exclude its leading lock icon.
      x: tile.x + promptRow.x + field.x + (field.width - width) / 2
      anchors.bottom: tile.top
      anchors.bottomMargin: Style.space(10)
      radius: root.cornerRadius
      color: root.background
      borderSpec: root.fieldBorderSpec
      visible: justificationText.text.length > 0

      Text {
        id: justificationText
        clip: true
        maximumLineCount: 3
        wrapMode: Text.Wrap
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Style.space(12)
        anchors.rightMargin: Style.space(12)
        text: root.authorizationLabel(root.currentMessage).replace(/[\r\n\u2028\u2029]+/g, " ")
        textFormat: Text.PlainText
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
      }
    }
  }
}
