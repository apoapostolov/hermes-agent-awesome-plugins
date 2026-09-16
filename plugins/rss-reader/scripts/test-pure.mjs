import fs from "node:fs";
import assert from "node:assert/strict";

const src = fs.readFileSync(new URL("../desktop/plugin.js", import.meta.url), "utf8");

function grab(name) {
  const start = src.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing ${name}`);
  let i = src.indexOf("{", start);
  let depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error(`unclosed ${name}`);
}

const bundle = [grab("profileFromOwner"), grab("cheapExcerpt"), grab("firstBodyImage"), grab("httpsSrc"), grab("imageKey"), grab("folderOf"), grab("folderTitle"), grab("groupFeedsByFolder"), grab("previewFeedOrder"), grab("previewNavFeeds"), grab("muteHitCount")].join("\n");
const fns = {};
new Function("exports", `${bundle}
exports.profileFromOwner = profileFromOwner;
exports.cheapExcerpt = cheapExcerpt;
exports.firstBodyImage = firstBodyImage;
exports.httpsSrc = httpsSrc;
exports.imageKey = imageKey;
exports.folderOf = folderOf;
exports.folderTitle = folderTitle;
exports.groupFeedsByFolder = groupFeedsByFolder;
exports.previewNavFeeds = previewNavFeeds;
exports.muteHitCount = muteHitCount;
`)(fns);

assert.equal(fns.profileFromOwner(JSON.stringify(["abc", "apo"])), "apo");
assert.equal(fns.profileFromOwner(JSON.stringify(["local", "apo"])), "apo");
assert.equal(fns.cheapExcerpt("<p>Hello&nbsp;world</p>"), "Hello world");
assert.equal(fns.firstBodyImage('intro ![](https://cdn.example.com/a.jpg) more'), "https://cdn.example.com/a.jpg");
assert.equal(fns.firstBodyImage('<img src="https://cdn.example.com/b.png">'), "https://cdn.example.com/b.png");
assert.equal(fns.httpsSrc("//cdn.example.com/x.jpg"), "https://cdn.example.com/x.jpg");
assert.equal(fns.imageKey("https://www.Example.com/pic-640x480.jpg?w=8"), fns.imageKey("https://example.com/pic.jpg"));
assert.notEqual(fns.imageKey("https://example.com/a.jpg"), fns.imageKey("https://example.com/b.jpg"));
assert.equal(fns.folderTitle(""), "Ungrouped");
assert.equal(fns.folderOf({ folder: "AI" }), "AI");
const grouped = fns.groupFeedsByFolder([
  { id: "1", folder: "AI", unread: 2 },
  { id: "2", folder: "", unread: 1 },
  { id: "3", folder: "AI", unread: 3 }
]);
assert.equal(grouped.length, 2);
assert.equal(grouped[0].title, "AI");
assert.equal(grouped[0].unread, 5);
assert.equal(grouped[1].title, "Ungrouped");
const moved = fns.previewNavFeeds(
  [{ id: "1", folder: "AI" }, { id: "2", folder: "News" }],
  "1",
  0,
  "News"
);
assert.equal(moved[0].id, "1");
assert.equal(moved[0].folder, "News");
assert.equal(fns.muteHitCount([
  { title: "Coupon dump", body: "buy now", feed_id: "a" },
  { title: "News", body: "plain", feed_id: "a" },
  { title: "Coupon", body: "ok", feed_id: "b" }
], { phrase: "coupon", feed_id: "a" }), 1);

console.log("ok", 17);
