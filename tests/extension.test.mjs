import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ext = require("../extension/spoti-skipper.js");

function mockSpicetify() {
  const calls = [];
  let volume = 0.5;
  let heart = false;
  const rec = (name) => () => calls.push(name);
  return {
    calls,
    get volume() { return volume; },
    notes: [],
    showNotification(t) { this.notes.push(t); },
    Player: {
      next: rec("next"), back: rec("back"), play: rec("play"), pause: rec("pause"),
      toggleHeart: () => { heart = !heart; calls.push("heart"); },
      getHeart: () => heart,
      seek: (ms) => calls.push("seek:" + ms), toggleShuffle: rec("shuffle"), toggleRepeat: rec("repeat"),
      getVolume: () => volume,
      setVolume: (v) => { volume = v; calls.push("setVolume"); },
      data: { item: { metadata: { title: "Song", artist_name: "Artist" } } },
    },
  };
}

test("next/previous map to Player.next/back", () => {
  const S = mockSpicetify();
  assert.equal(ext.runCommand(S, "next"), true);
  assert.equal(ext.runCommand(S, "previous"), true);
  assert.deepEqual(S.calls, ["next", "back"]);
});

test("volume is clamped to 0..1", () => {
  const S = mockSpicetify();
  for (let i = 0; i < 10; i++) ext.runCommand(S, "volume_up");
  assert.equal(S.volume, 1);
  for (let i = 0; i < 15; i++) ext.runCommand(S, "volume_down");
  assert.equal(S.volume, 0);
});

test("unknown command is rejected", () => {
  const S = mockSpicetify();
  assert.equal(ext.runCommand(S, "explode"), false);
  assert.deepEqual(S.calls, []);
});

test("handleMessage runs command, notifies and acks with track", async () => {
  const S = mockSpicetify();
  const sent = [];
  const r = ext.handleMessage(S, JSON.stringify({ type: "command", command: "next" }), (o) => sent.push(o));
  assert.equal(r, "next");
  assert.equal(S.notes.length, 1);
  await new Promise((res) => setTimeout(res, 800));
  assert.deepEqual(sent, [{ type: "ack", command: "next", track: "Artist — Song" }]);
});

test("handleMessage ignores garbage", () => {
  const S = mockSpicetify();
  assert.equal(ext.handleMessage(S, "not json", () => {}), null);
  assert.equal(ext.handleMessage(S, JSON.stringify({ type: "hello" }), () => {}), null);
  assert.deepEqual(S.calls, []);
});

test("like/unlike are idempotent", () => {
  const S = mockSpicetify();
  ext.runCommand(S, "like");
  ext.runCommand(S, "like");
  assert.equal(S.Player.getHeart(), true);
  ext.runCommand(S, "unlike");
  ext.runCommand(S, "unlike");
  assert.equal(S.Player.getHeart(), false);
  assert.deepEqual(S.calls, ["heart", "heart"]);
});

test("restart seeks to 0", () => {
  const S = mockSpicetify();
  ext.runCommand(S, "restart");
  assert.deepEqual(S.calls, ["seek:0"]);
});
