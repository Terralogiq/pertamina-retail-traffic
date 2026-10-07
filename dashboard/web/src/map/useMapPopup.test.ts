import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LegPopupLayer } from "./LegPopupLayer";
import { HIDE_DELAY_MS, createMapPopup } from "./useMapPopup";

const at = { lat: -7, lng: 110 };
const body = createElement("div");

function setup() {
  const layer = { show: vi.fn(), hide: vi.fn(), destroy: vi.fn() } satisfies LegPopupLayer;
  const popup = createMapPopup(() => layer);
  const doc = new EventTarget();
  const mapListeners = new Map<string, () => void>();
  const remove = vi.fn();
  const map = {
    addListener: vi.fn((name: string, fn: () => void) => {
      mapListeners.set(name, fn);
      return { remove };
    }),
  };
  return { layer, popup, doc, map, mapListeners, remove };
}

const press = (doc: EventTarget, key: string) => doc.dispatchEvent(Object.assign(new Event("keydown"), { key }));

describe("createMapPopup", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows a hover card and hides it after the delay", () => {
    const { layer, popup } = setup();
    popup.hover(at, body, 48);
    expect(layer.show).toHaveBeenCalledWith(at, body, { liftPx: 48 });
    popup.hideSoon();
    vi.advanceTimersByTime(HIDE_DELAY_MS - 1);
    expect(layer.hide).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(layer.hide).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending hide when the pointer enters something else", () => {
    const { layer, popup } = setup();
    popup.hover(at, body);
    popup.hideSoon();
    popup.hover(at, body);
    vi.advanceTimersByTime(HIDE_DELAY_MS * 2);
    expect(layer.hide).not.toHaveBeenCalled();
  });

  it("ignores hover and hideSoon while a card is pinned", () => {
    const { layer, popup } = setup();
    popup.togglePin("a", at, () => body);
    layer.show.mockClear();
    popup.hover(at, body);
    popup.hideSoon();
    vi.advanceTimersByTime(HIDE_DELAY_MS * 2);
    expect(layer.show).not.toHaveBeenCalled();
    expect(layer.hide).not.toHaveBeenCalled();
  });

  it("pins with a close callback, announces it, and a second toggle by the same owner closes it", () => {
    const { layer, popup } = setup();
    const render = vi.fn(() => body);
    popup.togglePin("a", at, render, 48);
    expect(layer.show).toHaveBeenCalledWith(at, body, { liftPx: 48, live: true });
    popup.togglePin("a", at, render);
    expect(layer.hide).toHaveBeenCalledTimes(1);
    // Closed: hover works again.
    popup.hover(at, body);
    expect(layer.show).toHaveBeenCalledTimes(2);
  });

  it("moves the pin to another owner without closing", () => {
    const { layer, popup } = setup();
    popup.togglePin("a", at, () => body);
    popup.togglePin("b", at, () => body);
    expect(layer.show).toHaveBeenCalledTimes(2);
    expect(layer.hide).not.toHaveBeenCalled();
  });

  it("the close callback handed to the card hides and unpins", () => {
    const { layer, popup } = setup();
    let close = () => {};
    popup.togglePin("a", at, (onClose) => {
      close = onClose;
      return body;
    });
    close();
    expect(layer.hide).toHaveBeenCalledTimes(1);
    popup.hover(at, body);
    expect(layer.show).toHaveBeenCalledTimes(2);
  });

  it("closes on Escape and on a click on the map, not on other keys", () => {
    const { layer, popup, doc, map, mapListeners } = setup();
    popup.bind(doc, map, vi.fn());
    popup.togglePin("a", at, () => body);
    press(doc, "Enter");
    expect(layer.hide).not.toHaveBeenCalled();
    press(doc, "Escape");
    expect(layer.hide).toHaveBeenCalledTimes(1);
    popup.togglePin("a", at, () => body);
    mapListeners.get("click")!();
    expect(layer.hide).toHaveBeenCalledTimes(2);
  });

  it("cleanup clears the hide timer, removes the listeners and destroys the layer", () => {
    const { layer, popup, doc, map, remove } = setup();
    const destroy = vi.fn();
    const unbind = popup.bind(doc, map, destroy);
    popup.hover(at, body);
    popup.hideSoon();
    unbind();
    vi.advanceTimersByTime(HIDE_DELAY_MS * 2);
    expect(layer.hide).not.toHaveBeenCalled();
    expect(remove).toHaveBeenCalledTimes(1);
    expect(destroy).toHaveBeenCalledTimes(1);
    press(doc, "Escape");
    expect(layer.hide).not.toHaveBeenCalled();
  });

  it("does nothing before the layer exists", () => {
    const popup = createMapPopup(() => null);
    expect(() => {
      popup.hover(at, body);
      popup.togglePin("a", at, () => body);
      popup.hide();
    }).not.toThrow();
  });
});
