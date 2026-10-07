import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Login from "./Login";

describe("Login", () => {
  const html = renderToStaticMarkup(<Login onSuccess={() => {}} />);

  it("labels the password input", () => {
    expect(html).toMatch(/<label[^>]*for="login-password"/);
    expect(html).toMatch(/<input[^>]*id="login-password"/);
  });

  it("announces errors through a single role=alert region", () => {
    expect(html.split('role="alert"').length - 1).toBe(1);
    expect(html).toMatch(/<p[^>]*id="login-error"[^>]*role="alert"/);
    expect(html).not.toContain("aria-live");
  });
});
