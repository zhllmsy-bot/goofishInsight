import {
  extractItemsFromResponse,
  extractPrice,
  extractSearchMetadata,
  extractTags,
  filterNonAdItems,
  formatPublishTime,
  sortByPrice,
  sortByPublishTime,
} from './index';
import type { SearchResponse } from './types';

const mockPriceArray = [
  { bold: false, text: '¥', type: 'sign' as const },
  { bold: false, text: '5500', type: 'integer' as const },
];

const mockFishTags = [
  {
    data: {
      content: '48分钟前降价',
      labelId: '756',
    },
  },
  {
    data: {
      content: '热销商品',
      labelId: '757',
    },
  },
];

const mockResponse: SearchResponse = {
  api: 'mtop.taobao.idlemtopsearch.pc.search',
  data: {
    resultInfo: {
      hasNextPage: true,
      searchResControlFields: {
        numFound: 100,
        maxPrice: 10000,
        minPrice: 100,
        hasItems: true,
      },
    },
    resultList: [
      {
        data: {
          item: {
            main: {
              clickParam: {
                arg1: 'Item',
                args: {
                  id: '123456',
                  price: '5500',
                  publishTime: '1774076690000',
                  seller_id: 'test_seller_id',
                  catId: '50025387',
                  tbCatId: '50014945',
                },
                page: 'Page_xySearchResult',
              },
              exContent: {
                itemId: '123456',
                title: '测试商品 MacBook Pro',
                price: mockPriceArray,
                picUrl: 'http://example.com/image.jpg',
                userNickName: '测试卖家',
                userAvatarUrl: 'http://example.com/avatar.jpg',
                area: '浙江',
                fishTags: {
                  r2: {
                    tagList: mockFishTags,
                  },
                },
                isAliMaMaAD: false,
                isAuction: false,
                showVideoIcon: false,
              },
            },
          },
        },
      },
      {
        data: {
          item: {
            main: {
              clickParam: {
                arg1: 'Item',
                args: {
                  id: '789012',
                  price: '3000',
                  publishTime: '1774076691000',
                  seller_id: 'test_seller_id_2',
                  catId: '50025387',
                  tbCatId: '50014945',
                },
                page: 'Page_xySearchResult',
              },
              exContent: {
                itemId: '789012',
                title: '广告商品',
                price: [
                  { bold: false, text: '¥', type: 'sign' as const },
                  { bold: false, text: '3000', type: 'integer' as const },
                ],
                picUrl: 'http://example.com/ad.jpg',
                userNickName: '广告卖家',
                userAvatarUrl: 'http://example.com/avatar.jpg',
                area: '北京',
                isAliMaMaAD: true,
                isAuction: false,
                showVideoIcon: false,
              },
            },
          },
        },
      },
    ],
  },
};

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function runSmokeChecks(): void {
  assert(extractPrice(mockPriceArray) === '5500', 'extractPrice should read the integer price');

  const tags = extractTags(mockFishTags);
  assert(
    JSON.stringify(tags) === JSON.stringify(['48分钟前降价', '热销商品']),
    'extractTags should keep non-empty tag content'
  );

  const metadata = extractSearchMetadata(mockResponse);
  assert(metadata.hasNextPage === true, 'extractSearchMetadata should read pagination state');
  assert(metadata.totalItems === 100, 'extractSearchMetadata should read totalItems');

  const items = extractItemsFromResponse(mockResponse);
  assert(items.length === 2, 'extractItemsFromResponse should return both mock items');
  assert(items[0].itemId === '123456', 'first extracted item id should match the source');

  const nonAdItems = filterNonAdItems(items);
  assert(nonAdItems.length === 1, 'filterNonAdItems should remove the ad item');

  const sortedByPrice = sortByPrice(items, true);
  assert(sortedByPrice[0].price === '3000', 'sortByPrice should order ascending');

  const sortedByTime = sortByPublishTime(items, true);
  assert(
    sortedByTime[0].publishTime >= sortedByTime[1].publishTime,
    'sortByPublishTime should order descending'
  );

  const timeLabel = formatPublishTime(Date.now() - 5 * 60 * 1000);
  assert(timeLabel.includes('分钟前'), 'formatPublishTime should format relative minutes');

  console.log('packages/utils smoke check passed');
}

runSmokeChecks();
