# M&A Comp Research Notes

This folder holds the manual biotech M&A comparable set used by the acquisition
screen.

Files:

- `comparable_deals.yaml`: high-confidence comp set intended for direct use by
  the acquisition screen.
- `deal_universe_2020_2026.yaml`: broader sourcing universe of big-pharma and
  large-biotech takeouts since 2020, with fit tags and official source URLs.
- `target_monitor.yaml`: named current or recently resolved public-target
  monitor for live M&A follow-up that should not be mixed blindly into
  completed-deal medians.

## Sourcing rule

For each deal, prefer:

1. Deal value or enterprise value from the acquirer or target transaction
   announcement.
2. Peak-sales framing from one of:
   - company investor materials,
   - sell-side / consensus estimates reported by Reuters, LSEG, Refinitiv, or
     major financial press,
   - management guidance when a numeric peak-year range is stated.

When only a range is published, use the midpoint and say so in `notes`.
When only a lower bound is published, use the lower bound and say so in `notes`.
If a clean peak-sales estimate is unavailable, store `ev_to_peak_sales`
directly once a reliable source reports the multiple.

## Seed status

`comparable_deals.yaml` now contains 26 public deals with defensible valuation
inputs. It is not yet at the target 30-50 deals because a
meaningful share of recent biotech acquisitions are platform/private deals where
public peak-sales estimates are not disclosed cleanly enough for a high-quality
comp set.

`deal_universe_2020_2026.yaml` is the working backlog for that gap: it is
broader than the screenable comp set and includes deals that are useful to know
about, but not always suitable for straight EV/peak-sales medians.

`target_monitor.yaml` is the parallel live-name tracker. Use it for current
public target candidates such as Revolution Medicines and Tango Therapeutics, or
to record that a named company such as Avidity has already moved into the closed
deal universe.

## Next candidates

These are the remaining non-screenable names where public-source peak-sales
disclosure is still not good enough for `comparable_deals.yaml` as of
2026-03-22:

- IDRx / GSK
- Anthos Therapeutics / Novartis
- Mariana Oncology / Novartis
