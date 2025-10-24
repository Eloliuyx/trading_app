export const toUTCTS = (dateStr: string): number => {
    // 输入 YYYY-MM-DD（Asia/Shanghai），转 UTC 秒级时间戳
    const [y,m,d] = dateStr.split('-').map(Number);
    // 构造本地 +08:00 的日期，再转 UTC
    const dt = new Date(Date.UTC(y, m - 1, d, 0, 0, 0)); // 00:00 UTC
    return Math.floor(dt.getTime() / 1000);
  };

  export const pct = (v: number) => `${Math.round(v * 100)}%`;
