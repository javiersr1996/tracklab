import { expect, test } from "vitest";
import sitemap from "../app/sitemap";

test("no URL is listed twice in the sitemap", () => {
  const urls = sitemap().map((e) => e.url);
  expect(urls.filter((u, i) => urls.indexOf(u) !== i)).toEqual([]);
});
