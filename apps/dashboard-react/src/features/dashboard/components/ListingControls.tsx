import type { ListingSortMode } from '../lib/listingViewModel';

type ListingControlsProps = {
  regionFilter: string;
  regionOptions: string[];
  sortMode: ListingSortMode;
  onRegionFilterChange: (value: string) => void;
  onSortModeChange: (value: ListingSortMode) => void;
};

export function ListingControls(props: ListingControlsProps) {
  return (
    <div className="listing-controls" aria-label="商品列表排序和筛选">
      <label className="listing-control">
        <span>排序</span>
        <select value={props.sortMode} onChange={(event) => props.onSortModeChange(event.target.value as ListingSortMode)}>
          <option value="opportunity">机会优先</option>
          <option value="price_asc">价格升序</option>
          <option value="latest">最新发布</option>
        </select>
      </label>
      <label className="listing-control">
        <span>地区</span>
        <select value={props.regionFilter} onChange={(event) => props.onRegionFilterChange(event.target.value)}>
          <option value="">全部地区</option>
          {props.regionOptions.map((region) => (
            <option key={region} value={region}>
              {region}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
