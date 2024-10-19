# Hackceler8 2024 Tooling

To install the tooling:

1. Copy `hack` folder and `src` folder into the game folder.
2. Run `pip install -r hack_requirements.txt`.
3. Put `import hack` to the top of `client.py` and you are good.

# Hacks

- [x] Restore textbox copy/paste/etc functionality
- [x] Player sprint optimization
- [x] Boss level replay and rewind
- [ ] Path finding?

## Map Manipulation

- [x] Zoom in/out with <kbd>Scroll</kbd> key
- [x] Drag with <kbd>Right</kbd> click (Use <kbd>Ctrl</kbd> to pan faster)
- [x] Press <kbd>C</kbd> once to center camera back to player, press twice to return normal scale

## UI Elements

- [x] Collision box
- [x] Show warp destination
- [x] Important entity connection

### Enemy

- [x] Show melee range (red/yellow: sees/doesn't see player)
- [x] Show shoot range (red/yellow/green: sees player/opposite direction/out of range)
- [x] Show shoot countdown (number and range visibility)
- [x] Show projectile projectile

### Portal

- [x] Show portal remain usage
- [x] Show portal destination
- [x] Show invisible portal

## Play/Replay

- [x] Save/Load inputs
- [x] Play/Step using <kbd>P</kbd>
- [x] Speed up/down using <kbd>,</kbd> and <kbd>.</kbd>
- [x] <kbd>K</kbd> toggle between Real-Time Mode and Simulation Mode (only if currently at 0 of simulation buffer)
- [x] Press <kbd>B</kbd> to submit to the server.