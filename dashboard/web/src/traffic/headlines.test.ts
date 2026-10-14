import { describe, expect, it } from "vitest";
import type { TypicalLeg } from "./api";
import { actionHeadline, delayPhrase, trafficHeadline } from "./headlines";

function leg(name: string, windows: TypicalLeg["windows"]): TypicalLeg {
  return { leg: name, day_kind: "weekday", hours: [], windows };
}

describe("action headlines", () => {
  it("says not enough days yet until the profile is ready", () => {
    const legs = [leg("approach", [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }])];
    expect(actionHeadline(false, legs, "weekday")).toBe("Not enough days yet.");
  });

  it("names the busiest window in minutes", () => {
    const legs = [
      leg("departure", [{ start_hour: 17, end_hour: 18, median_delay_s: 90 }]),
      leg("approach", [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }]),
    ];
    expect(actionHeadline(true, legs, "weekday")).toBe(
      "Approach is slowest 07:00–09:00, about 3 min slower than usual.",
    );
  });

  it("says there is no busy window once the profile is ready and none was found", () => {
    expect(actionHeadline(true, [leg("approach", [])], "weekend")).toBe("No busy hours on weekends.");
  });

  it("stays neutral when that day kind has no legs", () => {
    expect(actionHeadline(true, [], "weekend")).toBe("No readings for this day kind.");
  });

  it("builds the recent-traffic headline from weekday windows only", () => {
    expect(trafficHeadline(null)).toBeNull();
    expect(
      trafficHeadline({
        days: 6,
        ready: false,
        legs: [leg("approach", [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }])],
      }),
    ).toBe("Not enough days yet.");
    const weekday = leg("approach", [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }]);
    const weekend = { ...leg("departure", [{ start_hour: 10, end_hour: 12, median_delay_s: 240 }]), day_kind: "weekend" as const };
    expect(trafficHeadline({ days: 7, ready: true, legs: [weekend, weekday] })).toBe(
      "Weekdays: Approach is slowest 07:00–09:00, about 3 min slower than usual.",
    );
  });

  it("phrases a short delay in seconds and a negative delay as no delay", () => {
    expect(delayPhrase(40)).toBe("about 40 s slower than usual");
    expect(delayPhrase(-2)).toBe("no delay");
  });
});
