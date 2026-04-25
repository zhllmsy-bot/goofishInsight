/**
 * 使用示例：处理商品数据
 */

import {
  extractItemsFromResponse,
  extractSearchMetadata,
  filterNonAdItems,
  sortByPrice,
  sortByPublishTime,
  formatPublishTime,
  ExtractedItem,
} from './index';

// 示例：处理搜索响应
export function processSearchResponse(response: any) {
  // 提取商品列表
  const items = extractItemsFromResponse(response);

  // 提取元数据
  const metadata = extractSearchMetadata(response);

  // 过滤广告
  const nonAdItems = filterNonAdItems(items);

  // 按发布时间排序（最新优先）
  const sortedByTime = sortByPublishTime(nonAdItems, true);

  // 按价格排序（从低到高）
  const sortedByPriceAsc = sortByPrice(nonAdItems, true);

  // 按价格排序（从高到低）
  const sortedByPriceDesc = sortByPrice(nonAdItems, false);

  return {
    all: items,
    nonAd: nonAdItems,
    sortedByTime,
    sortedByPriceAsc,
    sortedByPriceDesc,
    metadata,
  };
}

// 示例：格式化商品信息
export function formatItemInfo(item: ExtractedItem) {
  return {
    id: item.itemId,
    title: item.title,
    price: `¥${item.price}`,
    seller: item.userNickName,
    location: item.area,
    publishedAt: formatPublishTime(item.publishTime),
    tags: item.tags.join(' | '),
    type: [
      item.isAd && '广告',
      item.isAuction && '拍卖',
      item.hasVideo && '有视频',
    ]
      .filter(Boolean)
      .join(', '),
  };
}

// 示例：筛选特定价格范围的商品
export function filterByPriceRange(
  items: ExtractedItem[],
  minPrice: number,
  maxPrice: number
): ExtractedItem[] {
  return items.filter((item) => {
    const price = parseFloat(item.price) || 0;
    return price >= minPrice && price <= maxPrice;
  });
}

// 示例：按关键词搜索标题
export function searchByKeyword(items: ExtractedItem[], keyword: string): ExtractedItem[] {
  const lowerKeyword = keyword.toLowerCase();
  return items.filter((item) =>
    item.title.toLowerCase().includes(lowerKeyword)
  );
}

// 示例：按地区筛选
export function filterByArea(items: ExtractedItem[], area: string): ExtractedItem[] {
  return items.filter((item) => item.area.includes(area));
}

// 示例：统计价格分布
export function getPriceStats(items: ExtractedItem[]) {
  const prices = items.map((item) => parseFloat(item.price) || 0);

  if (prices.length === 0) {
    return {
      min: 0,
      max: 0,
      avg: 0,
      median: 0,
    };
  }

  const sorted = prices.sort((a, b) => a - b);
  const sum = prices.reduce((acc, val) => acc + val, 0);
  const avg = sum / prices.length;
  const median =
    prices.length % 2 === 0
      ? (sorted[prices.length / 2 - 1] + sorted[prices.length / 2]) / 2
      : sorted[Math.floor(prices.length / 2)];

  return {
    min: sorted[0],
    max: sorted[sorted.length - 1],
    avg: Math.round(avg * 100) / 100,
    median,
  };
}

// 示例：统计地区分布
export function getAreaDistribution(items: ExtractedItem[]): Record<string, number> {
  const distribution: Record<string, number> = {};

  for (const item of items) {
    const area = item.area || '未知';
    distribution[area] = (distribution[area] || 0) + 1;
  }

  return distribution;
}

// 使用示例
/*
import searchResponse from './mock/data.json';

const processed = processSearchResponse(searchResponse);

console.log('总商品数:', processed.metadata.totalItems);
console.log('当前页商品数:', processed.all.length);
console.log('非广告商品数:', processed.nonAd.length);

// 显示前5个商品
processed.sortedByTime.slice(0, 5).forEach((item) => {
  console.log(formatItemInfo(item));
});

// 价格统计
const stats = getPriceStats(processed.nonAd);
console.log('价格统计:', stats);

// 地区分布
const areaDist = getAreaDistribution(processed.nonAd);
console.log('地区分布:', areaDist);
*/