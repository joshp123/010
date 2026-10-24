import { LRUCache } from './vendor/3d-tiles-renderer/build/index.core.js';

// The vendor's retention watermark cannot evict an atlas larger than the gap
// between minBytesSize and maxBytesSize. After a city jump that can leave the
// cache full, with every new request refused and no future update scheduled.
export class CityTileCache extends LRUCache {
  constructor(onRelease = () => {}) {
    super();
    this.onRelease = onRelease;
    this.pressureEvictions = 0;
  }

  unloadUnusedContent() {
    const before = this.itemSet.size;
    super.unloadUnusedContent();
    if (this.isFull()) {
      const unused = this.itemList.filter(tile => !this.isUsed(tile));
      const priority = this.unloadPriorityCallback || this.defaultPriorityCallback;
      unused.sort((a, b) => -priority(a, b));
      for (const tile of unused) {
        if (!this.isFull()) break;
        if (this.remove(tile)) this.pressureEvictions++;
      }
    }
    // Traversal refuses downloads before its deferred unload. Revisit the
    // current view after releasing bytes so those requests can be admitted.
    if (this.itemSet.size < before) this.onRelease();
  }
}
