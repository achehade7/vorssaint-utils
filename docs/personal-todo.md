Manual testing — leave unchecked until tested with real workflows:

- [ ] **Redesigned diff:** copy two texts → `diff` → Return. Edit either pane and confirm automatic highlighting, aligned lines, synchronized scrolling and undo with real OCR corrections and configuration changes. Automated/native tests and light/dark/small-window screenshots passed; real-workflow check remains.
- [ ] **One JSON button:** use **JSON** at the top-right of diff to format both sides. Try valid and invalid JSON, precise numbers and undo. Confirm saved clipboard history and source files stay unchanged. Automated precision, invalid-input and limit checks passed.
- [ ] **Payload inspector (`inspect`):** copy a real SAP JSON/XML payload, browse/search fields, edit **Source**, copy a value/path, and use **Open JSON** on escaped JSON strings. Include nested arrays and XML. Parser/native UI tests passed; real-payload check remains.
- [ ] **Screen compare (`screen compare`):** capture Before, change the screen, then capture After. Try the wipe divider, patterned difference overlay and image imports. Pixel comparison/native UI tests passed; the complete live capture workflow remains to be tested. This compares visible pixels locally, not hidden iFlow logic.
- [ ] **Drop to diff:** drag two real text/config files from Finder onto the island's **Before / After** targets. Confirm correct sides, filenames and comparison, and that neither source file changes. File-reading, limits, drop UI and editor tests passed.
- [ ] **Meeting reminders:** check real island notices at 10 minutes and 1 minute before a meeting, with no start-time banner. Click to join; ⌘Click should open **Prepare & join** and create/reuse the correct note. In `meet` and `note`, check calendar-day labels (Friday → Monday is 3 days), rounded-up minute countdowns and suggestions up to 5 minutes after a meeting starts. Timing, transport, labels and click routing were tested and Calendar access verified; the real reminder → join/note workflow remains to be tested.
- [ ] **Awake appearance:** open the coffee-cup card after using the app and after lock/unlock. Both switches should retain their white thumbs, the lid-closed option should remain visible, and Back should return Home. Restarting restored the missing thumbs on October 23; normal app/display captures and the user confirmed them visible, but the intermittent cause remains unconfirmed.

Deferred — revisit only if wanted:

- Focus scene: optional shortcut for a 25-minute timer, workspace G, and a purple progress edge.
- Automatic Do Not Disturb for that scene, with a timed expiry.
