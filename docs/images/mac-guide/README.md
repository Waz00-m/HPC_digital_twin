# Guide screenshot sources

Captured from the running local nine-bin demo on 26 November 2026. These are real browser screenshots, not native macOS installer or Terminal screenshots. The app screens are shared by the Mac and Windows editions; browser JSON formatting and timezone labels can differ.

- `warehouse-overview.jpg`: http://127.0.0.1:4321/ showing all three warehouses.
- `bin-details.jpg`: the same dashboard with bin-002 selected, cropped to its detail panel.
- `spoofer-controls.jpg`: http://127.0.0.1:4318/ with Warehouse B and bin-002 selected, cropped to the control and fleet area. No reading was published while taking the screenshots.
- `history-metrics.jpg`: http://127.0.0.1:4322/api/metrics with browser pretty printing, cropped to collector status and counts.
- `timed-samples.jpg`: http://127.0.0.1:4322/api/samples?thing_id=smartbin%3Abin-002&since=2026-11-26T07%3A41%3A00Z&until=2026-11-26T07%3A42%3A30Z with browser pretty printing. Actual sample IDs 2 and 14 both retain 20 kg and revision 20, with different observation times and the same original reading timestamp.

The Word builder is `docs/build_word_guide.py`. Its five figures use these JPEGs directly; sample values and screenshot labels have not been painted over or changed.
