const ID = 'busy-shortcuts'

export default {
  id: ID,
  name: 'Busy Shortcuts',
  description: 'Compact slash commands for interrupt, queue, and steer busy-input modes.',
  defaultEnabled: true,
  register() {
    // The command implementation lives in __init__.py. This desktop entry
    // makes the backend plugin visible in the desktop plugin toggle surface.
    return undefined
  }
}
