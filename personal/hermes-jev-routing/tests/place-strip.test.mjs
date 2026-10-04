import assert from 'node:assert/strict'
import test from 'node:test'

function el(slot) {
  const node = {
    slot,
    dataset: {},
    parentNode: null,
    nextSibling: null,
    children: [],
    insertAdjacentElement(where, child) {
      if (where !== 'afterend') throw new Error(where)
      child.parentNode = this.parentNode
      const kids = this.parentNode.children
      const index = kids.indexOf(this)
      kids.splice(index + 1, 0, child)
      this.nextSibling = child
      child.nextSibling = kids[index + 2] || null
      return child
    },
  }
  return node
}

function parentOf(...nodes) {
  const parent = { children: nodes }
  for (const node of nodes) node.parentNode = parent
  return parent
}

test('a model-change strip sits under the user prompt, not under the finished reply', () => {
  const user = el('aui_user-message-root')
  const assistant = el('aui_assistant-message-root')
  const parent = parentOf(user, assistant)
  const block = el('jev')
  block.dataset.jevStrip = '1'
  user.insertAdjacentElement('afterend', block)
  assert.equal(parent.children.map((node) => node.slot).join(','), 'aui_user-message-root,jev,aui_assistant-message-root')
  assert.equal(parent.children[1], block)
  assert.notEqual(parent.children.at(-1), block)
})
