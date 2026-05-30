<template>
  <div class="m-home">
    <!-- Balance card -->
    <div class="m-card balance-card">
      <div class="balance-label">USDC 可用余额</div>
      <div class="balance-value">${{ usdcBalance }}</div>
    </div>

    <!-- Quick actions -->
    <div class="m-card">
      <div class="card-title">快捷操作</div>
      <div class="action-grid">
        <div class="action-item" @click="$router.push('/m/btc')">
          <span class="action-icon">₿</span>
          <span class="action-label">BTC交易</span>
        </div>
        <div class="action-item" @click="$router.push('/m/sports')">
          <span class="action-icon"> </span>
          <span class="action-label">体育赛事</span>
        </div>
        <div class="action-item" @click="$router.push('/m/ai')">
          <span class="action-icon"> </span>
          <span class="action-label">AI预测</span>
        </div>
        <div class="action-item" @click="$router.push('/m/positions')">
          <span class="action-icon"> </span>
          <span class="action-label">持仓</span>
        </div>
      </div>
    </div>

    <!-- Positions summary -->
    <div class="m-card">
      <div class="card-title">持仓概览</div>
      <div v-if="loading" class="empty-hint">加载中...</div>
      <div v-else-if="positions.length === 0" class="empty-hint">暂无持仓</div>
      <div v-else>
        <div v-for="p in positions.slice(0, 5)" :key="p.asset" class="pos-row" @click="$router.push('/m/positions')">
          <div class="pos-info">
            <div class="pos-title">{{ p.title_zh || p.title }}</div>
            <div class="pos-meta">{{ p.size }} 份</div>
          </div>
          <div class="pos-value" :class="{ profit: parseFloat(p.cashPnl || 0) >= 0, loss: parseFloat(p.cashPnl || 0) < 0 }">
            ${{ parseFloat(p.currentValue || 0).toFixed(2) }}
          </div>
        </div>
        <div v-if="positions.length > 5" class="more-hint" @click="$router.push('/m/positions')">
          查看全部 {{ positions.length }} 个持仓 →
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { btcApi } from '../../api'

const usdcBalance = ref('--')
const positions = ref<any[]>([])
const loading = ref(true)

async function loadData() {
  loading.value = true
  try {
    const { data } = await btcApi.positions()
    const list = (data.positions || []).filter((p: any) => parseFloat(p.size || 0) > 0.000001 && !p.redeemable && !p.redeemed)
    positions.value = list
    const bal = data.balance
    if (bal && typeof bal === 'object') {
      const raw = bal.balance ?? bal.available ?? bal.available_balance ?? null
      usdcBalance.value = raw !== null ? Number(raw).toFixed(2) : '--'
    }
  } catch {} finally { loading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.m-home {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.m-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.balance-card {
  background: linear-gradient(135deg, #304156, #409eff);
  color: #fff;
}

.balance-label {
  font-size: 13px;
  opacity: 0.8;
  margin-bottom: 4px;
}

.balance-value {
  font-size: 28px;
  font-weight: bold;
}

.card-title {
  font-size: 15px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 12px;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.action-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.action-icon {
  font-size: 24px;
}

.action-label {
  font-size: 12px;
  color: #606266;
}

.pos-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
}

.pos-row:last-child {
  border-bottom: none;
}

.pos-info {
  flex: 1;
  min-width: 0;
}

.pos-title {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pos-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.pos-value {
  font-size: 14px;
  font-weight: bold;
  white-space: nowrap;
  margin-left: 12px;
}

.profit { color: #67c23a; }
.loss { color: #f56c6c; }

.empty-hint {
  text-align: center;
  color: #909399;
  font-size: 14px;
  padding: 20px 0;
}

.more-hint {
  text-align: center;
  color: #409eff;
  font-size: 13px;
  padding: 10px 0 0;
  cursor: pointer;
}
</style>
