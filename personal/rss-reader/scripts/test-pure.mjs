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

const bundle = [grab("profileFromOwner"), grab("cheapExcerpt"), grab("firstBodyImage"), grab("httpsSrc"), grab("imageKey"), grab("folderOf"), grab("folderTitle"), grab("groupFeedsByFolder"), grab("previewFolderOrder"), grab("previewFeedOrder"), grab("previewNavFeeds"), grab("applyFeedMove"), grab("muteScope"), grab("compactMuteScope"), grab("muteAppliesToArticle"), grab("isTagMute"), grab("muteTagKey"), grab("muteHidesArticle"), grab("muteHitCount"), grab("isDesignPreviewGrade"), grab("articleHasGrade"), grab("rememberGrade"), grab("applyCachedGrade"), grab("gradingTagFor"), grab("tagRank"), grab("sortArticlesByImportance"), grab("parseGradingTags"), grab("refreshButtonLabel"), grab("normalizeFolderName"), grab("folderNameTaken"), grab("remapMuteFolders"), grab("applyFolderAction"), grab("buildPreferenceSnapshot"), grab("interestPayloadJson"), grab("normalizeDefaultView"), grab("normalizeRefreshMinutes"), grab("pruneArticleCache"), grab("normalizeCacheKeepDays"), grab("pruneExpiredArticles"), grab("youtubeVideoId"), grab("isYoutubeArticle"), grab("youtubeEmbedSrc"), grab("youtubeTimeParam"), grab("parseYoutubeChapters"), grab("articleNeedsCapture"), grab("healthAgeLabel"), grab("healthNotice"), grab("isShareHref"), grab("htmlPageTitle"), grab("headingMatchesTitle"), grab("readableChromeKind"), grab("rssFindTokens"), grab("rssArticleFindHaystack"), grab("rssArticleFindScore"), grab("feedsearchCanonicalUrl"), grab("feedsearchIsFresh"), grab("feedsearchRank"), grab("feedsearchVisible"), grab("feedsearchMeta"), grab("folderContains"), grab("rememberUnreadTrail"), grab("unreadListWithTrail"), grab("youtubeSiteHost"), grab("youtubeFeedFromUrl"), grab("isYoutubePlaylistFeed"), grab("sortArticlesByTime"), grab("substackFeedFromUrl"), grab("youtubeChannelIdFromHtml"), grab("expandSubscribeUrl"), grab("feedWantsCapture"), grab("feedShowsTicker"), grab("feedTriState"), grab("parseTriState"), grab("normalizeUserAgent"), grab("userAgentPresetId"), grab("normalizeYoutubeCookies"), grab("youtubeCookieHeader"), grab("isYoutubeRequestUrl")].join(String.fromCharCode(10));
const fns = {};
new Function("exports", `const DEFAULT_GRADING_TAGS = [
  { key: "important", label: "IMPORTANT", color: "#d9534f", tint: 12, rank: 100 },
  { key: "interesting", label: "INTERESTING", color: "#d9a441", tint: 10, rank: 70 },
  { key: "normal", label: "", color: "", tint: 0, rank: 40 },
  { key: "spam", label: "SPAM", color: "#6b6b6b", tint: 10, rank: 10 }
];
const REFRESH_MINUTES = [5, 10, 15, 30, 60, 120, 180];
const CACHE_KEEP_DAYS = [7, 14, 30, 60, 90, 180, 365];
const USER_AGENT_PRESETS = [
  { id: "hermes", value: "HermesRSS/0.2" },
  { id: "chrome", value: "Mozilla/5.0 Chrome" }
];
const DEFAULT_USER_AGENT = USER_AGENT_PRESETS[0].value;
function currentYoutubeCookies() { return ""; }
${bundle}
exports.profileFromOwner = profileFromOwner;
exports.cheapExcerpt = cheapExcerpt;
exports.firstBodyImage = firstBodyImage;
exports.httpsSrc = httpsSrc;
exports.imageKey = imageKey;
exports.folderOf = folderOf;
exports.folderTitle = folderTitle;
exports.groupFeedsByFolder = groupFeedsByFolder;
exports.previewFolderOrder = previewFolderOrder;
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
exports.parseGradingTags = parseGradingTags;
exports.tagRank = tagRank;
exports.sortArticlesByImportance = sortArticlesByImportance;
exports.refreshButtonLabel = refreshButtonLabel;
exports.normalizeFolderName = normalizeFolderName;
exports.applyFolderAction = applyFolderAction;
exports.buildPreferenceSnapshot = buildPreferenceSnapshot;
exports.interestPayloadJson = interestPayloadJson;
exports.normalizeDefaultView = normalizeDefaultView;
exports.normalizeRefreshMinutes = normalizeRefreshMinutes;
exports.normalizeCacheKeepDays = normalizeCacheKeepDays;
exports.pruneExpiredArticles = pruneExpiredArticles;
exports.articleNeedsCapture = articleNeedsCapture;
exports.youtubeVideoId = youtubeVideoId;
exports.isYoutubeArticle = isYoutubeArticle;
exports.youtubeEmbedSrc = youtubeEmbedSrc;
exports.youtubeTimeParam = youtubeTimeParam;
exports.parseYoutubeChapters = parseYoutubeChapters;
exports.healthAgeLabel = healthAgeLabel;
exports.healthNotice = healthNotice;
exports.isShareHref = isShareHref;
exports.htmlPageTitle = htmlPageTitle;
exports.headingMatchesTitle = headingMatchesTitle;
exports.readableChromeKind = readableChromeKind;
exports.rssFindTokens = rssFindTokens;
exports.rssArticleFindHaystack = rssArticleFindHaystack;
exports.rssArticleFindScore = rssArticleFindScore;
exports.feedsearchCanonicalUrl = feedsearchCanonicalUrl;
exports.feedsearchRank = feedsearchRank;
exports.feedsearchVisible = feedsearchVisible;
exports.feedsearchMeta = feedsearchMeta;
exports.folderContains = folderContains;
exports.rememberUnreadTrail = rememberUnreadTrail;
exports.unreadListWithTrail = unreadListWithTrail;
exports.youtubeSiteHost = youtubeSiteHost;
exports.youtubeFeedFromUrl = youtubeFeedFromUrl;
exports.isYoutubePlaylistFeed = isYoutubePlaylistFeed;
exports.sortArticlesByTime = sortArticlesByTime;
exports.substackFeedFromUrl = substackFeedFromUrl;
exports.youtubeChannelIdFromHtml = youtubeChannelIdFromHtml;
exports.expandSubscribeUrl = expandSubscribeUrl;
exports.feedWantsCapture = feedWantsCapture;
exports.feedShowsTicker = feedShowsTicker;
exports.feedTriState = feedTriState;
exports.parseTriState = parseTriState;
exports.normalizeUserAgent = normalizeUserAgent;
exports.userAgentPresetId = userAgentPresetId;
exports.normalizeYoutubeCookies = normalizeYoutubeCookies;
exports.youtubeCookieHeader = youtubeCookieHeader;
exports.isYoutubeRequestUrl = isYoutubeRequestUrl;
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
const folderRanked = fns.groupFeedsByFolder([
  { id: "1", folder: "AI", unread: 1 },
  { id: "2", folder: "News", unread: 1 }
], ["News", "AI"]);
assert.deepEqual(folderRanked.map(group => group.key), ["News", "AI"]);
const folderPreview = fns.previewFolderOrder([
  { key: "", title: "Ungrouped" },
  { key: "AI", title: "AI" },
  { key: "News", title: "News" }
], "News", 0);
assert.deepEqual(folderPreview.map(group => group.key), ["", "News", "AI"]);
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

const parsed = fns.parseGradingTags("```tags\nimportant | IMPORTANT | #d9534f | 12 | 100\nspam | SPAM | #6b6b6b | 10 | 10\n```");
assert.equal(parsed[0].rank, 100);
assert.equal(parsed[1].rank, 10);
assert.equal(fns.tagRank(parsed, "important"), 100);
const ordered = fns.sortArticlesByImportance([
  { id: "a", grade: { level: "spam" }, published_at: "2026-09-16" },
  { id: "b", grade: { level: "important" }, published_at: "2026-09-01" },
  { id: "c", grade: { level: "important" }, published_at: "2026-09-10" },
  { id: "d", published_at: "2026-09-20" }
], parsed);
assert.equal(ordered.map((a) => a.id).join(""), "cbad");
assert.equal(fns.refreshButtonLabel(0, 1), "Refresh");
assert.equal(fns.refreshButtonLabel(0, Date.now()), "Refresh");
assert.equal(fns.refreshButtonLabel(1e12, 1e12 + 5 * 6e4), "Refresh \u00b7 5m");
assert.equal(fns.normalizeFolderName("  News  "), "News");
const lib = { feeds: [{ id: "1", folder: "AI" }], folders: [], filters: { mutes: [{ folders: ["AI"] }] } };
fns.applyFolderAction(lib, { action: "create", name: "News" });
assert.equal(lib.folders.join(","), "News");
fns.applyFolderAction(lib, { action: "create", name: "Games" });
fns.applyFolderAction(lib, { action: "reorder", order: ["Games", "News", "AI"] });
assert.equal(lib.folders.join(","), "Games,News,AI");
fns.applyFolderAction(lib, { action: "rename", from: "AI", to: "ML" });
assert.equal(lib.feeds[0].folder, "ML");
assert.equal(lib.filters.mutes[0].folders.join(","), "ML");
fns.applyFolderAction(lib, { action: "delete", from: "ML", dest: "" });
assert.equal(lib.feeds[0].folder, "");
const extras = fns.groupFeedsByFolder(lib.feeds, ["Empty"]);
assert.equal(extras.some((g) => g.key === "Empty" && g.feeds.length === 0), true);
const snap = fns.buildPreferenceSnapshot({
  feeds: [{ id: "1", title: "AI News", folder: "AI" }],
  articles: [
    { id: "a", feed_id: "1", title: "Keep", is_saved: true, is_read: true, body: "<p>Hello</p>", url: "https://example.com/a" },
    { id: "b", feed_id: "1", title: "Skip", is_saved: false, is_read: false, body: "x" }
  ],
  filters: { mutes: [{ phrase: "crypto", folders: ["AI"], hits: 2 }] }
});
assert.equal(snap.saved_count, 1);
assert.equal(snap.saved[0].title, "Keep");
assert.equal(snap.feeds[0].unread, 1);
assert.equal(snap.mutes[0].phrase, "crypto");
const interestJson = fns.interestPayloadJson({
  skill: "rss-reader-plugin",
  saved_count: 80,
  saved: Array.from({ length: 80 }, (_, i) => ({ title: `Article ${i} ${"x".repeat(180)}`, excerpt: "y".repeat(220), url: `https://example.com/${i}/${"z".repeat(280)}` })),
  feeds: Array.from({ length: 100 }, (_, i) => ({ title: `Feed ${i}`, folder: "News", total: 100, saved: 1, read: 50, unread: 50 })),
  mutes: Array.from({ length: 50 }, (_, i) => ({ phrase: `mute-${i}`, folders: ["News"], hits: i })),
  tags: [{ key: "important", label: "IMPORTANT", rank: 100 }]
});
assert.ok(interestJson.length <= 16000);
const interestPayload = JSON.parse(interestJson);
assert.equal(interestPayload.saved_count, 80);
assert.ok(interestPayload.omitted.saved + interestPayload.omitted.feeds + interestPayload.omitted.mutes > 0);
assert.equal(fns.normalizeDefaultView("saved"), "saved");
assert.equal(fns.normalizeDefaultView("nope"), "all");
assert.equal(fns.normalizeRefreshMinutes(15), 15);
assert.equal(fns.normalizeRefreshMinutes(180), 180);
assert.equal(fns.normalizeRefreshMinutes(7), 5);
assert.equal(fns.normalizeRefreshMinutes(1440), 180);
assert.equal(fns.normalizeRefreshMinutes("nope"), 15);
assert.equal(fns.normalizeCacheKeepDays(), 14);
assert.equal(fns.normalizeCacheKeepDays(14), 14);
assert.equal(fns.normalizeCacheKeepDays(365), 365);
assert.equal(fns.normalizeCacheKeepDays(20), 14);
const keepLib = {
  articles: [
    { id: "old", feed_id: "f1", identity: "old", published_at: "2026-01-01T00:00:00.000Z", is_saved: false, url: "https://x/old" },
    { id: "live", feed_id: "f1", identity: "live", published_at: "2026-01-01T00:00:00.000Z", is_saved: false, url: "https://x/live" },
    { id: "star", feed_id: "f1", identity: "star", published_at: "2026-01-01T00:00:00.000Z", is_saved: true, url: "https://x/star" },
    { id: "new", feed_id: "f1", identity: "new", published_at: "2026-09-10T00:00:00.000Z", is_saved: false, url: "https://x/new" }
  ],
  articleCache: { "https://x/old": { body: "old" }, "https://x/live": { body: "live" } }
};
fns.pruneExpiredArticles(keepLib, "f1", ["live"], 14, Date.parse("2026-09-20T00:00:00.000Z"));
assert.deepEqual(keepLib.articles.map((a) => a.id).sort(), ["live", "new", "star"]);
assert.equal("https://x/old" in keepLib.articleCache, false);
assert.equal("https://x/live" in keepLib.articleCache, true);
assert.equal(fns.articleNeedsCapture({ url: "https://x", captured: false, body: "short" }), true);
assert.equal(fns.articleNeedsCapture({ url: "https://x", captured: true, body: "x".repeat(900) }), false);
assert.equal(fns.articleNeedsCapture({ url: "https://x", captured: true, body: "short" }), true);
assert.equal(fns.articleNeedsCapture({ url: "https://x", captured: true, body: "short", captureGaveUp: true }), false);
assert.equal(fns.articleNeedsCapture({}), false);
assert.equal(fns.youtubeVideoId("https://www.youtube.com/watch?v=abcdefghijk"), "abcdefghijk");
assert.equal(fns.youtubeVideoId("https://youtu.be/abcdefghijk"), "abcdefghijk");
assert.equal(fns.youtubeVideoId("yt:video:abcdefghijk"), "abcdefghijk");
assert.equal(fns.isYoutubeArticle({ url: "https://www.youtube.com/watch?v=abcdefghijk" }), true);
assert.equal(fns.articleNeedsCapture({ url: "https://www.youtube.com/watch?v=abcdefghijk", captured: false, body: "short" }), false);
assert.equal(fns.youtubeTimeParam("125"), 125);
assert.equal(fns.youtubeTimeParam("1h2m3s"), 3723);
assert.equal(fns.youtubeEmbedSrc("abcdefghijk", 90), "https://www.youtube.com/embed/abcdefghijk?feature=oembed&playsinline=1&enablejsapi=1&widget_referrer=https%3A%2F%2Fhermes-agent.nousresearch.com%2F&start=90");
assert.deepEqual(fns.parseYoutubeChapters("0:00 Intro\n1:53 Reading the essay\n4:46 Sponsor").map(row => [row.seconds, row.title]), [[0, "Intro"], [113, "Reading the essay"], [286, "Sponsor"]]);
assert.deepEqual(fns.parseYoutubeChapters("no stamps here"), []);
assert.equal(fns.healthAgeLabel(null, "m"), "never");
const health = fns.healthNotice([
  { title: "Broken", error: "timeout", refresh_age_minutes: 5, newest_age_days: 1, unread: 1 },
  { title: "Stale", error: "", refresh_age_minutes: 100, newest_age_days: 1, unread: 2 },
  { title: "Quiet", error: "", refresh_age_minutes: 5, newest_age_days: 8, unread: 0 }
], 15);
assert.match(health, /3 feeds/);
assert.match(health, /3 unread/);
assert.match(health, /1 error/);
assert.match(health, /1 stale refresh/);
assert.match(health, /1 quiet for 7d\+?/);
assert.equal(fns.htmlPageTitle("<title>  Flash floods  | The Verge</title>"), "Flash floods | The Verge");
assert.equal(fns.headingMatchesTitle("Flash floods", "Flash floods | The Verge"), true);
assert.equal(fns.headingMatchesTitle("A later section", "Flash floods | The Verge"), false);
assert.equal(fns.readableChromeKind("Recent articles"), "stop");
assert.equal(fns.readableChromeKind("Sponsored by: WorkOS — auth.md"), "skip");
assert.equal(fns.readableChromeKind("Subscribers only Learn more"), "skip");
assert.equal(fns.readableChromeKind("What a delight."), "");
assert.equal(fns.isShareHref("https://www.facebook.com/sharer.php?u=https://techcrunch.com/x"), true);
assert.equal(fns.isShareHref("https://www.linkedin.com/in/naderlikeladder"), false);
assert.equal(fns.readableChromeKind("[https://www.facebook.com/sharer.php?u=https://x](https://www.facebook.com/sharer.php?u=https://x)"), "skip");
assert.equal(fns.readableChromeKind("[AI](https://techcrunch.com/category/artificial-intelligence/), [nvidia](https://techcrunch.com/tag/nvidia/)"), "skip");
assert.equal(fns.readableChromeKind("Most Popular"), "stop");
assert.deepEqual(fns.rssFindTokens("that rss article about paizo"), ["paizo"]);
assert.equal(fns.rssArticleFindScore({ title: "Weekly news", body: "Paizo announced a Pathfinder reprint." }, "RPG", ["paizo"]), 1);
assert.equal(fns.rssArticleFindScore({ title: "Paizo Q&A", body: "interview" }, "News", ["paizo"]), 2);
assert.equal(fns.rssArticleFindScore({ title: "Unrelated", body: "nope" }, "News", ["paizo"]), 0);
const now = Date.parse("2026-09-19T00:00:00Z");
assert.equal(fns.feedsearchCanonicalUrl("http://www.Example.com/feed/"), "https://example.com/feed");
const ranked = fns.feedsearchRank([
  { url: "http://example.com/feed/", title: "Old", item_count: 20, velocity: 1, score: 10, last_updated: "2026-09-10T00:00:00Z", bozo: 0 },
  { url: "https://www.example.com/feed", title: "New", item_count: 20, velocity: 2, score: 40, last_updated: "2026-09-18T00:00:00Z", bozo: 0 },
  { url: "https://dead.example.com/rss", title: "Dead", item_count: 9, velocity: 0, score: 80, last_updated: "2019-02-20T00:00:00Z", bozo: 0 },
  { url: "https://broken.example.com/rss", title: "Broken", item_count: 1, velocity: 1, score: 90, last_updated: "2026-09-18T00:00:00Z", bozo: 1 }
], now, 90);
assert.equal(ranked.length, 3);
assert.equal(ranked[0].title, "New");
assert.equal(fns.feedsearchVisible(ranked, false).map(row => row.title).join(","), "New");
assert.equal(fns.feedsearchVisible(ranked, true).length, 3);
assert.match(fns.feedsearchMeta(ranked[0]), /20 items/);
assert.equal(fns.folderContains("News/AI", "News"), true);
assert.equal(fns.folderContains("News", "News"), true);
assert.equal(fns.folderContains("AI", "News"), false);
assert.equal(fns.folderContains("", ""), true);
assert.equal(fns.folderContains("News", ""), false);
assert.equal(fns.youtubeFeedFromUrl("https://www.youtube.com/channel/UC1234567890abcdefghijk"), "https://www.youtube.com/feeds/videos.xml?channel_id=UC1234567890abcdefghijk");
assert.equal(fns.youtubeFeedFromUrl("https://www.youtube.com/playlist?list=PLabcdefghijk"), "https://www.youtube.com/feeds/videos.xml?playlist_id=PLabcdefghijk");
assert.equal(fns.youtubeFeedFromUrl("https://www.youtube.com/watch?v=abcdefghijk&list=PLabcdefghijk"), "https://www.youtube.com/feeds/videos.xml?playlist_id=PLabcdefghijk");
assert.equal(fns.isYoutubePlaylistFeed("https://www.youtube.com/feeds/videos.xml?playlist_id=PLabcdefghijk"), true);
assert.equal(fns.isYoutubePlaylistFeed("https://www.youtube.com/feeds/videos.xml?channel_id=UC1234567890abcdefghijk"), false);
assert.deepEqual(fns.sortArticlesByTime([{ id: "old", published_at: "2020-01-01T00:00:00Z" }, { id: "new", published_at: "2021-01-01T00:00:00Z" }], true).map((row) => row.id), ["old", "new"]);
assert.deepEqual(fns.sortArticlesByTime([{ id: "old", published_at: "2020-01-01T00:00:00Z" }, { id: "new", published_at: "2021-01-01T00:00:00Z" }], false).map((row) => row.id), ["new", "old"]);
assert.equal(fns.substackFeedFromUrl("https://example.substack.com/p/hello"), "https://example.substack.com/feed");
assert.equal(fns.expandSubscribeUrl("https://www.youtube.com/user/Veritasium"), "https://www.youtube.com/feeds/videos.xml?user=Veritasium");
assert.equal(fns.youtubeChannelIdFromHtml('meta "channelId":"UC1234567890123456789012"'), "UC1234567890123456789012");
assert.equal(fns.feedWantsCapture({ fullCapture: false }, { fullCapture: true }), false);
assert.equal(fns.feedWantsCapture({ fullCapture: true }, { fullCapture: false }), true);
assert.equal(fns.feedShowsTicker({ ticker: false }), false);
assert.equal(fns.parseTriState(fns.feedTriState(undefined)), null);
assert.deepEqual(fns.rememberUnreadTrail(fns.rememberUnreadTrail(fns.rememberUnreadTrail([], { id: "a" }), { id: "b" }), { id: "c" }).map(row => row.id), ["a", "b", "c"]);
assert.deepEqual(fns.rememberUnreadTrail([{ id: "a" }, { id: "b" }, { id: "c" }], { id: "b" }).map(row => row.id), ["a", "b"]);
assert.deepEqual(fns.unreadListWithTrail([{ id: "c" }, { id: "d" }], [{ id: "a" }, { id: "b" }, { id: "c" }]).map(row => row.id), ["a", "b", "c", "d"]);
assert.equal(fns.normalizeUserAgent(""), "HermesRSS/0.2");
assert.equal(fns.normalizeUserAgent("Mozilla/5.0 Chrome"), "Mozilla/5.0 Chrome");
assert.equal(fns.normalizeUserAgent("bad\nagent"), "HermesRSS/0.2");
assert.equal(fns.userAgentPresetId("Mozilla/5.0 Chrome"), "chrome");
assert.equal(fns.userAgentPresetId("MyBot/1.0"), "custom");
assert.equal(fns.normalizeYoutubeCookies(""), "");
assert.equal(fns.youtubeCookieHeader("LOGIN_INFO=abc"), "LOGIN_INFO=abc");
assert.equal(fns.youtubeCookieHeader("# Netscape\n.youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tabc"), "LOGIN_INFO=abc");
assert.equal(fns.isYoutubeRequestUrl("https://www.youtube.com/watch?v=abcdefghijk"), true);

console.log("ok", 104);
