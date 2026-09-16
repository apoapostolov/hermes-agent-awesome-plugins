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

const bundle = [grab("profileFromOwner"), grab("cheapExcerpt"), grab("firstBodyImage"), grab("httpsSrc"), grab("imageKey")].join("\n");
const fns = {};
new Function("exports", `${bundle}\nexports.profileFromOwner = profileFromOwner;\nexports.cheapExcerpt = cheapExcerpt;\nexports.firstBodyImage = firstBodyImage;\nexports.httpsSrc = httpsSrc;\nexports.imageKey = imageKey;`)(fns);

assert.equal(fns.profileFromOwner(JSON.stringify(["abc", "apo"])), "apo");
assert.equal(fns.profileFromOwner(JSON.stringify(["local", "apo"])), "apo");
assert.equal(fns.cheapExcerpt("<p>Hello&nbsp;world</p>"), "Hello world");
assert.equal(fns.firstBodyImage('intro ![](https://cdn.example.com/a.jpg) more'), "https://cdn.example.com/a.jpg");
assert.equal(fns.firstBodyImage('<img src="https://cdn.example.com/b.png">'), "https://cdn.example.com/b.png");
assert.equal(fns.httpsSrc("//cdn.example.com/x.jpg"), "https://cdn.example.com/x.jpg");
assert.equal(fns.imageKey("https://www.Example.com/pic-640x480.jpg?w=8"), fns.imageKey("https://example.com/pic.jpg"));
assert.notEqual(fns.imageKey("https://example.com/a.jpg"), fns.imageKey("https://example.com/b.jpg"));

console.log("ok", 8);
