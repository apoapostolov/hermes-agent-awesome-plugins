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

const bundle = [grab("profileFromOwner"), grab("cheapExcerpt"), grab("firstBodyImage"), grab("httpsSrc"), grab("imageKey"), grab("folderOf"), grab("folderTitle"), grab("groupFeedsByFolder"), grab("previewFeedOrder"), grab("previewNavFeeds"), grab("applyFeedMove"), grab("muteScope"), grab("compactMuteScope"), grab("muteAppliesToArticle"), grab("muteHitCount"), grab("isDesignPreviewGrade"), grab("articleHasGrade"), grab("rememberGrade"), grab("applyCachedGrade")].join("\n");
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
exports.applyFeedMove = applyFeedMove;
exports.muteScope = muteScope;
exports.compactMuteScope = compactMuteScope;
exports.muteAppliesToArticle = muteAppliesToArticle;
exports.muteHitCount = muteHitCount;
exports.isDesignPreviewGrade = isDesignPreviewGrade;
exports.articleHasGrade = articleHasGrade;
exports.rememberGrade = rememberGrade;
exports.applyCachedGrade = applyCachedGrade;
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
const previewStay = fns.previewNavFeeds(
  [{ id: "1", folder: "AI" }, { id: "2", folder: "News" }],
  "1",
  0,
  "News"
);
assert.equal(previewStay[0].id, "1");
assert.equal(previewStay[0].folder, "AI");
const moved = fns.applyFeedMove(
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
assert.equal(fns.muteAppliesToArticle({ folders: ["AI"] }, { feed_id: "1" }, [{ id: "1", folder: "AI" }]), true);
assert.equal(fns.compactMuteScope(
  [{ id: "1", folder: "AI" }, { id: "2", folder: "AI" }],
  ["1", "2"],
  []
).folders.join(","), "AI");

assert.equal(fns.isDesignPreviewGrade({ reason: "Design preview: tint sample" }), true);
assert.equal(fns.articleHasGrade({ grade: { level: "important", reason: "Design preview: tint sample" } }), false);
assert.equal(fns.articleHasGrade({ grade: { level: "spam", reason: "affiliate bait" } }), true);
const gradeLib = { gradeCache: {} };
fns.rememberGrade(gradeLib, { url: "https://x/a", identity: "g1", grade: { level: "spam", reason: "affiliate bait" } });
const reused = { url: "https://x/a", identity: "g1" };
assert.equal(fns.applyCachedGrade(gradeLib, reused), true);
assert.equal(reused.grade.level, "spam");
const fake = { grade: { level: "important", reason: "Design preview: gone" } };
assert.equal(fns.applyCachedGrade(gradeLib, fake), true);
assert.equal(fake.grade, undefined);

console.log("ok", 21);
