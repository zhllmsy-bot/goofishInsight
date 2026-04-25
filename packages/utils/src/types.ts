/**
 * 闲鱼商品数据类型定义
 */

export interface PriceItem {
  bold: boolean;
  fontFamily?: string;
  marginBottom?: number;
  marginLeft?: number;
  text: string;
  textColor?: string;
  textSize?: number;
  type: 'sign' | 'integer';
}

export interface FishTagData {
  gradientColors?: string[];
  color?: string;
  borderRadius?: string;
  size?: string;
  labelId?: string;
  lineHeight?: string;
  gradientDirection?: string;
  gradientType?: string;
  type?: string;
  content?: string;
  height?: string;
  leftImage?: {
    marginRight?: string;
    width?: string;
    url?: string;
    height?: string;
    marginLeft?: string;
  };
}

export interface FishTag {
  data: FishTagData;
  utParams?: {
    args: Record<string, string>;
    arg1: string;
  };
}

export interface UserFishShopLabelTag {
  data: {
    color?: string;
    content?: string;
    lineHeight?: string;
    size?: string;
    type?: string;
  };
}

export interface ClickParamArgs {
  price?: string;
  id?: string;
  item_id?: string;
  item_type?: string;
  seller_id?: string;
  publishTime?: string;
  picWidth?: string;
  picHeight?: string;
  keyword?: string;
  [key: string]: string | undefined;
}

export interface ClickParam {
  arg1: string;
  args: ClickParamArgs;
  page: string;
}

export interface DetailParams {
  picWidth?: string;
  itemId?: string;
  itemType?: string;
  picHeight?: string;
  userNick?: string;
  soldPrice?: string;
  isVideo?: string;
  title?: string;
}

export interface ExContent {
  area?: string;
  detailPageType?: string;
  detailParams?: DetailParams;
  fishTags?: {
    r2?: {
      tagList: FishTag[];
      config?: {
        mutualLabelBizGroup?: string;
      };
    };
  };
  hideUserInfo?: boolean;
  isAliMaMaAD?: boolean;
  isAuction?: boolean;
  itemId?: string;
  picHeight?: number;
  picUrl?: string;
  picWidth?: number;
  placeholderColor?: string;
  price?: PriceItem[];
  priceTag?: unknown[];
  richTitle?: Array<{
    data: {
      bold?: boolean;
      fontWeight?: string;
      lineHeight?: number;
      text?: string;
      textColor?: string;
      textSize?: number;
    };
    type: string;
  }>;
  showVideoIcon?: boolean;
  title?: string;
  titleRowType?: string;
  userActiveUrl?: string;
  userAvatarUrl?: string;
  userFishShopLabel?: {
    config?: Record<string, string>;
    tagList: UserFishShopLabelTag[];
  };
  userIdentityShow?: string;
  userIsUseFishShopCard?: boolean;
  userNickName?: string;
  want?: string;
}

export interface ItemMain {
  clickParam: ClickParam;
  exContent: ExContent;
  targetUrl?: string;
}

export interface ResultItem {
  data: {
    item: {
      main: ItemMain;
    };
    template?: {
      name: string;
      url: string;
      version: string;
    };
  };
  style?: string;
  type?: string;
}

export interface SearchResponse {
  api: string;
  data: {
    appBar?: Record<string, unknown>;
    filterBar?: Record<string, unknown>;
    needDecryptKeys?: unknown[];
    resultInfo?: {
      hasNextPage?: boolean;
      searchResControlFields?: {
        hasItems?: boolean;
        maxPrice?: number;
        minPrice?: number;
        nextPage?: boolean;
        numFound?: number;
        [key: string]: unknown;
      };
      [key: string]: unknown;
    };
    resultList: ResultItem[];
    [key: string]: unknown;
  };
}

export interface ExtractedItem {
  itemId: string;
  title: string;
  price: string;
  picUrl: string;
  userNickName: string;
  userAvatarUrl: string;
  area: string;
  publishTime: number;
  tags: string[];
  sellerId: string;
  catId: string;
  tbCatId: string;
  isAuction: boolean;
  isAd: boolean;
  hasVideo: boolean;
}