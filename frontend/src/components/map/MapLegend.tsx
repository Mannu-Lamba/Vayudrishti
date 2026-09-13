export default function MapLegend() {
  return (
    <div className="map-legend-box" data-testid="map-legend">
      <span><i className="lg-dot" />Selected cyclone</span>
      <span><i className="lg-dot lg-dot-other" />Other systems · colour = category</span>
      <span><i className="lg-line" />Historical track</span>
      <span><i className="lg-line lg-dash" />Predicted track</span>
      <span><i className="lg-cone" />Prediction uncertainty</span>
      <span><i className="lg-risk" />Risk zone</span>
    </div>
  );
}
