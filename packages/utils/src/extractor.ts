import {
  SearchResponse,
  ResultItem,
  ExtractedItem,
  ItemMain,
  PriceItem,
  FishTag,
} from './types';

/**
 * 从价格数组中提取价格数字
 */
export function extractPrice(priceArray?: PriceItem[]): string {
  if (!priceArray || priceArray.length === 0) {
    return '0';
  }

  const priceItem = priceArray.find((item) => item.type === 'integer');
  return priceItem?.text || '0';
}

/**
 * 从标签列表中提取标签内容
 */
export function extractTags(fishTags?: FishTag[]): string[] {
  if (!fishTags || fishTags.length === 0) {
    return [];
  }

  return fishTags
    .map((tag) => tag.data?.content)
    .filter((content): content is string => Boolean(content));
}

/**
 * 转换时间戳为数字（毫秒）
 */
export function extractTimestamp(timestampStr?: string): number {
  if (!timestampStr) {
    return 0;
  }
  return parseInt(timestampStr, 10);
}

/**
 * 从单个商品项提取核心字段
 */
export function extractItemFromResult(resultItem: ResultItem): ExtractedItem | null {
  try {
    const main: ItemMain = resultItem.data?.item?.main;

    if (!main) {
      return null;
    }

    const { exContent, clickParam } = main;

    if (!exContent) {
      return null;
    }

    const itemId = exContent.itemId || clickParam.args.id || '';
    const title = exContent.title || '';
    const price = extractPrice(exContent.price);
    const picUrl = exContent.picUrl || '';
    const userNickName = exContent.userNickName || '';
    const userAvatarUrl = exContent.userAvatarUrl || '';
    const area = exContent.area || '';
    const publishTime = extractTimestamp(clickParam.args.publishTime);
    const tags = extractTags(exContent.fishTags?.r2?.tagList);
    const sellerId = clickParam.args.seller_id || '';
    const catId = clickParam.args.catId || '';
    const tbCatId = clickParam.args.tbCatId || '';
    const isAuction = exContent.isAuction || false;
    const isAd = exContent.isAliMaMaAD || false;
    const hasVideo = exContent.showVideoIcon || false;

    return {
      itemId,
      title,
      price,
      picUrl,
      userNickName,
      userAvatarUrl,
      area,
      publishTime,
      tags,
      sellerId,
      catId,
      tbCatId,
      isAuction,
      isAd,
      hasVideo,
    };
  } catch (error) {
    console.error('Error extracting item:', error);
    return null;
  }
}

/**
 * 从搜索响应中提取所有商品项
 */
export function extractItemsFromResponse(response: SearchResponse): ExtractedItem[] {
  const resultList = response?.data?.resultList;

  if (!resultList || !Array.isArray(resultList)) {
    return [];
  }

  const items: ExtractedItem[] = [];

  for (const resultItem of resultList) {
    const extractedItem = extractItemFromResult(resultItem);
    if (extractedItem) {
      items.push(extractedItem);
    }
  }

  return items;
}

/**
 * 获取搜索元数据
 */
export function extractSearchMetadata(response: SearchResponse) {
  const resultInfo = response?.data?.resultInfo;
  const controlFields = resultInfo?.searchResControlFields;

  return {
    hasNextPage: resultInfo?.hasNextPage || controlFields?.nextPage || false,
    totalItems: controlFields?.numFound || 0,
    maxPrice: controlFields?.maxPrice || 0,
    minPrice: controlFields?.minPrice || 0,
    hasItems: controlFields?.hasItems || false,
  };
}

/**
 * 格式化发布时间为可读字符串
 */
export function formatPublishTime(timestamp: number): string {
  if (!timestamp) {
    return '未知';
  }

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) {
    return '刚刚';
  } else if (diffMins < 60) {
    return `${diffMins}分钟前`;
  } else if (diffHours < 24) {
    return `${diffHours}小时前`;
  } else if (diffDays < 30) {
    return `${diffDays}天前`;
  } else {
    return date.toLocaleDateString('zh-CN');
  }
}

/**
 * 过滤掉广告商品
 */
export function filterNonAdItems(items: ExtractedItem[]): ExtractedItem[] {
  return items.filter((item) => !item.isAd);
}

/**
 * 按价格排序
 */
export function sortByPrice(items: ExtractedItem[], ascending: boolean = true): ExtractedItem[] {
  return [...items].sort((a, b) => {
    const priceA = parseFloat(a.price) || 0;
    const priceB = parseFloat(b.price) || 0;
    return ascending ? priceA - priceB : priceB - priceA;
  });
}

/**
 * 按发布时间排序
 */
export function sortByPublishTime(items: ExtractedItem[], descending: boolean = true): ExtractedItem[] {
  return [...items].sort((a, b) => {
    return descending ? b.publishTime - a.publishTime : a.publishTime - b.publishTime;
  });
}