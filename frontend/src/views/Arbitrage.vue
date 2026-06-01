<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="篮子套利" name="basket">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>事件套利扫描</span>
              <div>
                <el-button size="small" @click="showHelp = true" style="margin-right:8px">套利说明</el-button>
                <span style="margin-right:8px">篮子预算</span>
                <el-input-number v-model="precheckBudget" :min="5" :max="10000" :step="5" size="small" style="width:120px;margin-right:8px" />
                <span style="margin-right:8px">偏差阈值:</span>
                <el-input-number v-model="threshold" :min="0.01" :max="0.5" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button type="primary" size="small" @click="scan" :loading="loading">扫描</el-button>
              </div>
            </div>
          </template>

          <el-table :data="results" size="small" v-loading="loading" @row-click="selectRow" highlight-current-row>
            <el-table-column label="事件" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column label="YES总和" width="100">
              <template #default="{ row }">{{ row.yes_sum.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="预算毛利" width="110">
              <template #default="{ row }">${{ Number(row.estimated_profit || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="毛利率" width="90">
              <template #default="{ row }">{{ Number(row.estimated_profit_pct || 0).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="方向" width="100">
              <template #default="{ row }">
                <el-tag :type="row.direction === 'SELL_YES' ? 'danger' : 'success'" size="small">{{ row.direction }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可执行" width="90">
              <template #default="{ row }">
                <el-tag :type="basketStatusType(row)" size="small">{{ basketStatusLabel(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="完整性" width="100">
              <template #default="{ row }">
                <el-tag :type="row.integrity?.ok ? 'success' : 'danger'" size="small">
                  {{ row.integrity?.captured_count || row.markets?.length || 0 }}/{{ row.integrity?.official_count || '?' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="到期" width="120">
              <template #default="{ row }">{{ row.end_date_bj || '-' }}</template>
            </el-table-column>
	            <el-table-column label="操作" width="270">
	              <template #default="{ row }">
	                <el-button size="small" @click.stop="expandDetail(row)">详情</el-button>
	                <el-button size="small" type="info" link @click.stop="showAdvice(row, 'basket', precheckBudget)">AI提示</el-button>
	                <el-button size="small" type="primary" link @click.stop="precheckRow(row)">预检</el-button>
	                <el-button size="small" type="success" link :loading="actionLoading === actionKey(row, 'basket')" :disabled="!row.executable || row.direction !== 'BUY_YES'" @click.stop="buyBasket(row, true)">一键买</el-button>
	              </template>
	            </el-table-column>
          </el-table>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>AI 套利分析</template>
          <el-row :gutter="12" align="middle">
            <el-col :span="8">
              <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%">
                <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!selected || !aiConfigId" style="width:100%">AI 套利分析</el-button>
            </el-col>
          </el-row>
          <div v-if="prediction" style="margin-top:12px;white-space:pre-wrap;font-size:13px">{{ prediction }}</div>
          <div v-if="!selected" style="margin-top:8px;color:#999;font-size:12px">请先点击表格行选择一个套利机会</div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="盘口滑点" name="slippage">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>低滑点盘口</span>
              <div>
                <span style="margin-right:8px">金额</span>
                <el-input-number v-model="slippageParams.amount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">最大滑点%</span>
                <el-input-number v-model="slippageParams.max_slippage_pct" :min="0.1" :max="20" :step="0.1" size="small" style="width:110px;margin-right:8px" />
                <el-button size="small" type="success" :disabled="slippageSelected.length === 0" :loading="slippageBatchLoading" @click="buySelectedSlippage">批量买选中</el-button>
                <el-button size="small" type="primary" :loading="slippageLoading" @click="loadSlippage">扫描</el-button>
              </div>
            </div>
          </template>
          <el-alert type="info" show-icon :closable="false" style="margin-bottom:12px" title="操作提示" description="这里不是套利利润，毛利是假设该结果最终兑付 1 USDC 时的兑付毛利。价格冲击为 0 表示本次金额按当前盘口不会推高均价；买入或批量买入都会在后端重新预检并用 FOK 提交。" />
          <el-table :data="slippageResults" size="small" v-loading="slippageLoading" max-height="560" row-key="token_id" @selection-change="onSlippageSelection">
            <el-table-column type="selection" width="42" fixed="left" />
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="direction" label="方向" width="70" />
            <el-table-column label="均价" width="80">
              <template #default="{ row }">${{ row.depth.avg_price.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="最差价" width="80">
              <template #default="{ row }">${{ row.depth.worst_price.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="价格冲击" width="90">
              <template #default="{ row }">
                {{ row.depth.slippage_pct.toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column label="兑付毛利" width="100">
              <template #default="{ row }">${{ Number(row.depth.gross_profit_if_win || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="兑付ROI" width="90">
              <template #default="{ row }">{{ Number(row.depth.gross_roi_if_win_pct || 0).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="可买份额" width="100">
              <template #default="{ row }">{{ row.depth.shares.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="24h量" width="110">
              <template #default="{ row }">${{ Math.round(row.volume_24h).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="end_date_bj" label="到期" width="120" />
	            <el-table-column label="操作" width="130" fixed="right">
	              <template #default="{ row }">
	                <el-button size="small" type="info" link @click="showAdvice(row, 'slippage', slippageParams.amount, { max_slippage_pct: slippageParams.max_slippage_pct })">AI</el-button>
	                <el-button size="small" type="primary" :loading="actionLoading === actionKey(row, 'slippage')" @click="buySlippage(row)">买入</el-button>
	              </template>
	            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="同题价差" name="cross">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>跨事件同题价差</span>
              <div>
                <span style="margin-right:8px">双边预算</span>
                <el-input-number v-model="quickAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">价差</span>
                <el-input-number v-model="crossParams.min_spread" :min="0.01" :max="0.8" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="crossLoading" @click="loadCross">扫描</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" show-icon :closable="false" style="margin-bottom:12px" title="双边操作提示" description="预算毛利按上方“双边预算”估算，最大盘口只作参考。同题重复盘买候选 YES + 参考 NO；到期包含盘买后到期 YES + 前到期 NO。交易所不保证跨市场原子成交，提交后仍要核对订单。" />
          <el-table :data="crossResults" size="small" v-loading="crossLoading" max-height="560">
            <el-table-column label="主题" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.topic_zh || row.topic }}</div>
                <div style="font-size:12px;color:#909399">{{ row.strategy_label || row.relation_type || '-' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="价差" width="90">
              <template #default="{ row }">{{ (row.spread * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="预算成本" width="110">
              <template #default="{ row }">
                <el-tag :type="row.executable ? 'success' : 'warning'" size="small">
                  {{ row.executable ? `$${Number(row.pair_depth?.total_cost || row.pair_depth?.capacity_usdc || 0).toFixed(2)}` : '观察' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="预算毛利" width="120">
              <template #default="{ row }">
                <template v-if="row.executable">
                  ${{ Number(row.pair_depth?.expected_profit || 0).toFixed(2) }}
                  <span style="color:#909399">({{ Number(row.pair_depth?.expected_profit_pct || 0).toFixed(2) }}%)</span>
                </template>
                <span v-else style="color:#909399">无正毛利</span>
              </template>
            </el-table-column>
            <el-table-column label="最大盘口" width="110">
              <template #default="{ row }">${{ Number(row.pair_depth?.max_capacity_usdc || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="买入 YES" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.buy_candidate.question_zh }}</div>
                <div style="font-size:12px;color:#f56c6c">到期 {{ row.buy_candidate.end_date_bj || '-' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="对冲 NO" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.sell_reference.question_zh }}</div>
                <div style="font-size:12px;color:#909399">到期 {{ row.sell_reference.end_date_bj || '-' }}</div>
              </template>
            </el-table-column>
	            <el-table-column label="操作" width="165" fixed="right">
	              <template #default="{ row }">
	                <el-button size="small" type="info" link @click="showAdvice(row, 'cross', quickAmount, { min_profit_pct: minProfitPct })">AI</el-button>
	                <el-button size="small" type="success" :loading="actionLoading === actionKey(row, 'cross-smart')" :disabled="!row.executable" @click="buyCrossHedge(row)">按预算双边</el-button>
	              </template>
	            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="奖励做市" name="rewards">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>奖励市场做市面板</span>
              <div>
                <span style="margin-right:8px">单边金额</span>
                <el-input-number v-model="makerAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <el-button size="small" type="warning" :loading="cancelAllLoading" @click="cancelAllOpenOrders">紧急全撤</el-button>
                <el-button size="small" type="primary" :loading="rewardsLoading" @click="loadRewards">扫描</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" show-icon :closable="false" style="margin-bottom:12px" title="做市提示" description="奖励做市不是直接吃单套利。按钮会在 YES/NO 两边各挂一个 post-only 买单，金额不足奖励最小份额时会拒绝提交；挂出后仍要到订单页观察是否 scoring、是否需要撤单。" />
          <el-table :data="rewardsResults" size="small" v-loading="rewardsLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.question_zh || row.question }}</template>
            </el-table-column>
            <el-table-column label="买/卖" width="115">
              <template #default="{ row }">${{ row.best_bid.toFixed(3) }} / ${{ row.best_ask.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="点差" width="80">
              <template #default="{ row }">{{ (row.spread * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="奖励要求" width="150">
              <template #default="{ row }">{{ row.rewards_min_size }}份 / {{ (row.rewards_max_spread * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.fit ? 'success' : 'warning'" size="small">{{ row.fit ? '达标' : '偏宽' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="end_date_bj" label="到期" width="120" />
	            <el-table-column label="操作" width="165" fixed="right">
	              <template #default="{ row }">
	                <el-button size="small" type="info" link @click="showAdvice(row, 'rewards', makerAmount)">AI</el-button>
	                <el-button size="small" type="primary" :loading="actionLoading === actionKey(row, 'maker')" @click="quoteMaker(row)">挂双边</el-button>
	              </template>
	            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="临近结算" name="resolution">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>临近结算 / UMA 状态</span>
              <div>
                <span style="margin-right:8px">买入金额</span>
                <el-input-number v-model="quickAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">小时</span>
                <el-input-number v-model="resolutionParams.hours" :min="1" :max="168" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="resolutionLoading" @click="loadResolution">扫描</el-button>
              </div>
            </div>
          </template>
          <el-table :data="resolutionResults" size="small" v-loading="resolutionLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.question_zh || row.question }}</template>
            </el-table-column>
            <el-table-column label="YES" width="80">
              <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="剩余小时" width="90">
              <template #default="{ row }">{{ row.hours_left ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="end_date_bj" label="结束" width="110" />
            <el-table-column prop="uma_status" label="状态" width="120" />
            <el-table-column label="下单" width="80">
              <template #default="{ row }">
                <el-tag :type="row.can_buy ? 'success' : 'info'" size="small">{{ row.can_buy ? '可下单' : '观察' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="24h量" width="110">
              <template #default="{ row }">${{ Math.round(row.volume_24h).toLocaleString() }}</template>
            </el-table-column>
	            <el-table-column label="操作" width="185" fixed="right">
	              <template #default="{ row }">
	                <el-button size="small" type="info" link @click="showAdvice(row, 'resolution', quickAmount)">AI</el-button>
	                <el-button size="small" type="primary" link :disabled="!row.can_buy" :loading="actionLoading === actionKey(row, 'res-yes')" @click="buyOutcome(row, 0, 'YES')">买YES</el-button>
	                <el-button size="small" type="primary" link :disabled="!row.can_buy || !row.token_ids?.[1]" :loading="actionLoading === actionKey(row, 'res-no')" @click="buyOutcome(row, 1, 'NO')">买NO</el-button>
	              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="持仓对冲" name="hedges">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>持仓对冲建议</span>
              <div>
                <el-button size="small" type="danger" :disabled="hedgeSelected.length === 0" :loading="hedgeCloseLoading" @click="closeSelectedHedges">批量 FOK 平仓</el-button>
                <el-button size="small" type="warning" :loading="cancelAllLoading" @click="cancelAllOpenOrders">紧急全撤</el-button>
                <el-button size="small" type="primary" :loading="hedgeLoading" @click="loadHedges">刷新</el-button>
              </div>
            </div>
          </template>
          <el-table :data="hedgeResults" size="small" v-loading="hedgeLoading" max-height="560" row-key="asset" @selection-change="onHedgeSelection">
            <el-table-column type="selection" width="42" fixed="left" />
            <el-table-column label="持仓" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="outcome" label="结果" width="90" />
            <el-table-column label="份额" width="90">
              <template #default="{ row }">{{ row.size.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="价格" width="80">
              <template #default="{ row }">${{ row.price.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="盈亏" width="90">
              <template #default="{ row }">{{ row.pnl >= 0 ? '+' : '' }}${{ row.pnl.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="risk" label="类型" width="110" />
            <el-table-column label="到期" width="120">
              <template #default="{ row }">{{ row.end_date_bj || '-' }}</template>
            </el-table-column>
            <el-table-column prop="action" label="建议" show-overflow-tooltip />
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="danger" :loading="actionLoading === actionKey(row, 'sell')" @click="sellHolding(row)">卖出</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="BTC提醒" name="btc">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>BTC 短周期动量提醒</span>
              <div>
                <span style="margin-right:8px">买入金额</span>
                <el-input-number v-model="quickAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">最小 edge</span>
                <el-input-number v-model="btcParams.min_edge" :min="0.01" :max="0.5" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="btcLoading" @click="loadBtcAlerts">扫描</el-button>
                <el-button size="small" :loading="btcNotifyLoading" @click="notifyBtc">推送</el-button>
              </div>
            </div>
          </template>
          <el-table :data="btcResults" size="small" v-loading="btcLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="series_label" label="周期" width="80" />
            <el-table-column prop="action" label="动作" width="80" />
            <el-table-column label="Edge" width="90">
              <template #default="{ row }">{{ (row.edge * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="概率" width="130">
              <template #default="{ row }">UP {{ (row.signal.prob_up * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column prop="end_time_bj" label="截止" width="110" />
	            <el-table-column label="操作" width="125" fixed="right">
	              <template #default="{ row }">
	                <el-button size="small" type="info" link @click="showAdvice(row, 'btc', quickAmount)">AI</el-button>
	                <el-button size="small" type="primary" :loading="actionLoading === actionKey(row, 'btc')" @click="buyBtcAlert(row)">买入</el-button>
	              </template>
	            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="新闻催化" name="news">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>新闻催化雷达</span>
              <div>
                <span style="margin-right:8px">买入金额</span>
                <el-input-number v-model="quickAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <el-select v-model="newsParams.category" size="small" style="width:110px;margin-right:8px">
                  <el-option label="政治" value="politics" />
                  <el-option label="体育" value="sports" />
                  <el-option label="加密" value="crypto" />
                  <el-option label="全部" value="all" />
                </el-select>
                <span style="margin-right:8px">小时</span>
                <el-input-number v-model="newsParams.lookback_hours" :min="6" :max="168" size="small" style="width:100px;margin-right:8px" />
                <el-select v-model="aiConfigId" placeholder="AI模型" size="small" style="width:130px;margin-right:8px">
                  <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
                <el-button size="small" type="primary" :loading="newsLoading" @click="loadNews">扫描</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" show-icon :closable="false" style="margin-bottom:12px" title="新闻雷达提示" description="列表按市场到期时间从近到远排列；AI复核会真实调用所选模型判断新闻和规则相关性，快捷买入仍会走规则风控和 FOK。" />
          <el-table :data="newsResults" size="small" v-loading="newsLoading" max-height="560">
            <el-table-column label="市场" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.title_zh || row.title }}</div>
                <div style="font-size:12px;color:#909399">{{ row.latest_headline_zh || row.latest_headline || '暂无近期新闻标题' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="热度" width="105">
              <template #default="{ row }">
                <el-tag :type="row.signal_score >= 70 ? 'danger' : row.signal_score >= 45 ? 'warning' : 'info'" size="small">
                  {{ row.signal_level }} {{ Number(row.signal_score || 0).toFixed(0) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="新闻" width="80">
              <template #default="{ row }">{{ row.news_count }}</template>
            </el-table-column>
            <el-table-column label="YES/NO" width="105">
              <template #default="{ row }">${{ Number(row.yes_price || 0).toFixed(3) }} / ${{ Number(row.no_price || 0).toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="24h量" width="110">
              <template #default="{ row }">${{ Math.round(row.volume_24h || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="latest_news_bj" label="最新新闻" width="100" />
            <el-table-column prop="end_date_bj" label="到期" width="110" />
            <el-table-column label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="info" link :loading="intelAiLoading === actionKey(row, 'news-ai')" @click="runIntelAiReview(row, 'news')">AI复核</el-button>
                <el-button size="small" type="primary" link :loading="actionLoading === actionKey(row, 'news-yes')" @click="buyNews(row, 0, 'YES')">买YES</el-button>
                <el-button size="small" type="primary" link :disabled="!row.token_ids?.[1]" :loading="actionLoading === actionKey(row, 'news-no')" @click="buyNews(row, 1, 'NO')">买NO</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="赛程雷达" name="schedule">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>体育赛程匹配</span>
              <div>
                <span style="margin-right:8px">未来天数</span>
                <el-input-number v-model="scheduleParams.days_ahead" :min="1" :max="30" size="small" style="width:100px;margin-right:8px" />
                <el-switch v-model="scheduleParams.include_unsupported" size="small" active-text="显示小联赛/电竞" style="margin-right:8px" />
                <el-select v-model="aiConfigId" placeholder="AI模型" size="small" style="width:130px;margin-right:8px">
                  <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
                <el-button size="small" type="primary" :loading="scheduleLoading" @click="loadSchedule">匹配</el-button>
              </div>
            </div>
          </template>
          <el-alert type="info" show-icon :closable="false" style="margin-bottom:12px" title="赛程过滤口径" description="ESPN 可覆盖的核心联赛会尝试匹配具体赛程；小联赛、电竞、板球会单独标为非 ESPN 覆盖，关闭开关可只看核心联赛。" />
          <el-table :data="scheduleResults" size="small" v-loading="scheduleLoading" max-height="560">
            <el-table-column label="Polymarket 事件" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column label="联赛" width="80">
              <template #default="{ row }">{{ row.league || row.league_guess || '-' }}</template>
            </el-table-column>
            <el-table-column label="匹配比赛" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">{{ row.game || row.teams || '-' }}</template>
            </el-table-column>
            <el-table-column prop="game_time_bj" label="比赛时间" width="110" />
            <el-table-column prop="game_status" label="状态" width="115" />
            <el-table-column label="风险" width="90">
              <template #default="{ row }">
                <el-tag :type="riskTagType(row.risk_level)" size="small">{{ row.risk_level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="YES/NO" width="105">
              <template #default="{ row }">
                <span v-if="row.token_ids?.length">${{ Number(row.yes_price || 0).toFixed(3) }} / ${{ Number(row.no_price || 0).toFixed(3) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="action" label="处理建议" min-width="220" show-overflow-tooltip />
            <el-table-column label="操作" width="235" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="info" link :loading="intelAiLoading === actionKey(row, 'schedule-ai')" @click="runIntelAiReview(row, 'schedule')">AI复核</el-button>
                <el-button size="small" type="primary" link :disabled="!row.can_buy" :loading="actionLoading === actionKey(row, 'schedule-yes')" @click="buySchedule(row, 0, 'YES')">买YES</el-button>
                <el-button size="small" type="primary" link :disabled="!row.can_buy || !row.token_ids?.[1]" :loading="actionLoading === actionKey(row, 'schedule-no')" @click="buySchedule(row, 1, 'NO')">买NO</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="聪明钱" name="smart">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>聪明钱钱包流向</span>
              <div>
                <span style="margin-right:8px">跟买金额</span>
                <el-input-number v-model="quickAmount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">小时</span>
                <el-input-number v-model="smartParams.lookback_hours" :min="1" :max="168" size="small" style="width:90px;margin-right:8px" />
                <span style="margin-right:8px">最小额</span>
                <el-input-number v-model="smartParams.min_notional" :min="1" :max="100000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">样本</span>
                <el-input-number v-model="smartParams.limit" :min="50" :max="5000" :step="500" size="small" style="width:120px;margin-right:8px" />
                <span style="margin-right:8px">钱包</span>
                <el-input-number v-model="smartParams.top_wallets" :min="3" :max="80" :step="5" size="small" style="width:100px;margin-right:8px" />
                <span style="margin-right:8px">刷新秒</span>
                <el-input-number v-model="smartAutoSeconds" :min="0" :max="600" :step="5" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="smartLoading" @click="loadSmartMoney">扫描</el-button>
              </div>
            </div>
          </template>
          <el-alert type="warning" show-icon :closable="false" style="margin-bottom:12px" title="跟单提示" :description="smartReport?.note || '会分页抓取更多公开成交并去重；聪明钱可能是对冲、做市或分批交易，只做观察信号。'" />
          <el-table :data="smartWallets" size="small" v-loading="smartLoading" max-height="560">
            <el-table-column type="expand">
              <template #default="{ row }">
                <el-table :data="row.recent_trades || []" size="small">
                  <el-table-column prop="timestamp_bj" label="时间" width="95" />
                  <el-table-column prop="side" label="方向" width="70" />
                  <el-table-column label="市场" show-overflow-tooltip>
                    <template #default="{ row: trade }">{{ trade.title_zh || trade.title }}</template>
                  </el-table-column>
                  <el-table-column prop="outcome" label="结果" width="90" />
                  <el-table-column label="金额" width="90">
                    <template #default="{ row: trade }">${{ Number(trade.notional || 0).toFixed(2) }}</template>
                  </el-table-column>
                  <el-table-column label="价格" width="80">
                    <template #default="{ row: trade }">${{ Number(trade.price || 0).toFixed(3) }}</template>
                  </el-table-column>
                </el-table>
              </template>
            </el-table-column>
            <el-table-column label="钱包" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <div>{{ row.pseudonym || row.name || row.wallet }}</div>
                <div style="font-size:12px;color:#909399">{{ row.wallet }}</div>
              </template>
            </el-table-column>
            <el-table-column label="评分" width="80">
              <template #default="{ row }">{{ Number(row.smart_score || 0).toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="成交额" width="100">
              <template #default="{ row }">${{ Number(row.total_notional || 0).toFixed(0) }}</template>
            </el-table-column>
            <el-table-column label="买/卖" width="125">
              <template #default="{ row }">${{ Number(row.buy_notional || 0).toFixed(0) }} / ${{ Number(row.sell_notional || 0).toFixed(0) }}</template>
            </el-table-column>
            <el-table-column prop="trades_count" label="笔数" width="70" />
            <el-table-column label="历史胜率" width="95">
              <template #default="{ row }">{{ row.closed_win_rate == null ? '-' : `${Number(row.closed_win_rate).toFixed(1)}%` }}</template>
            </el-table-column>
            <el-table-column label="最新BUY" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_buy_trade?.title_zh || row.last_buy_trade?.title || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="info" link @click="showAdvice(row, 'smart_money', quickAmount)">AI</el-button>
                <el-button size="small" type="primary" :disabled="!row.last_buy_trade" :loading="actionLoading === actionKey(row, 'smart-follow')" @click="followSmartMoney(row)">跟买BUY</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showHelp" title="套利说明" width="650">
      <div style="line-height:1.8;font-size:14px">
        <h3>什么是 Polymarket 事件套利？</h3>
        <p>一个负风险事件下多个结果互斥，买入所有 YES 的同等份额后，理论上最终会有一个结果兑付 1 USDC。</p>

        <h3>套利原理</h3>
        <ul>
          <li><strong>YES卖价总和 < 1.0</strong>：可逐项买入全部 YES，理论到期兑付 1 USDC</li>
          <li><strong>YES买价总和 > 1.0</strong>：只有在已有库存或完整做市流程下才适合卖出全部 YES</li>
        </ul>

        <h3>风险提示</h3>
        <ul>
          <li>套利需要同时买入/卖出多个市场，单边执行有价格变动风险</li>
          <li>流动性不足可能导致滑点，实际利润低于理论值</li>
          <li>交易手续费会侵蚀利润，偏差太小时不建议操作</li>
        </ul>
      </div>
    </el-dialog>

	    <el-dialog v-model="showDetail" title="套利详情" width="820">
      <el-descriptions :column="2" border size="small" v-if="selected">
        <el-descriptions-item label="事件">{{ selected.title_zh || selected.title }}</el-descriptions-item>
        <el-descriptions-item label="YES总和">{{ selected.yes_sum.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="偏差">{{ selected.deviation.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="预算毛利">${{ Number(selected.estimated_profit || 0).toFixed(2) }}（{{ Number(selected.estimated_profit_pct || 0).toFixed(2) }}%）</el-descriptions-item>
        <el-descriptions-item label="到期时间">{{ selected.end_date_bj || '-' }}</el-descriptions-item>
        <el-descriptions-item label="池子完整性">
          <el-tag :type="selected.integrity?.ok ? 'success' : 'danger'" size="small">
            {{ selected.integrity?.captured_count || selected.markets?.length || 0 }}/{{ selected.integrity?.official_count || '?' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="建议方向">
          <el-tag :type="selected.direction === 'SELL_YES' ? 'danger' : 'success'">{{ selected.direction }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="执行提示">{{ selected.execution_note || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-form inline size="small" style="margin:12px 0">
        <el-form-item label="篮子预算 ($)">
          <el-input-number v-model="precheckBudget" :min="5" :max="10000" :step="5" style="width:130px" />
        </el-form-item>
        <el-form-item label="最低毛利%">
          <el-input-number v-model="minProfitPct" :min="0" :max="50" :step="0.1" :precision="1" style="width:120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="precheckLoading" @click="precheckSelectedBasket">篮子预检</el-button>
          <el-button type="success" :loading="basketBuyLoading" :disabled="!selected?.executable || selected?.direction !== 'BUY_YES'" @click="buyBasket(selected)">一键买入篮子</el-button>
        </el-form-item>
      </el-form>
      <el-alert v-if="basketCheck" :type="basketCheck.fillable ? 'success' : 'warning'" show-icon :closable="false" style="margin-bottom:12px" :description="basketCheck.note">
        <template #title>
          按预算 ${{ basketCheckBudget || basketCheck.budget_usdc }} 预检：直接成本 ${{ basketCheck.total_cost }}，影子估算 ${{ basketCheck.shadow_cost || 0 }}，理论兑付 ${{ basketCheck.payout_if_complete }}，预估毛利 ${{ basketCheck.estimated_profit }}（{{ basketCheck.estimated_profit_pct }}%）
        </template>
      </el-alert>
      <el-table v-if="basketCheck?.shadow_legs?.length" :data="basketCheck.shadow_legs" size="small" style="margin-bottom:12px">
        <el-table-column label="影子补腿市场" show-overflow-tooltip>
          <template #default="{ row }">{{ row.question_zh || row.question }}</template>
        </el-table-column>
        <el-table-column label="建议挂价" width="100">
          <template #default="{ row }">${{ Number(row.suggested_price || 0).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="份额" width="90">
          <template #default="{ row }">{{ Number(row.target_shares || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="估算成本" width="100">
          <template #default="{ row }">${{ Number(row.estimated_cost || 0).toFixed(2) }}</template>
        </el-table-column>
      </el-table>
      <el-table :data="selected?.markets || []" size="small">
        <el-table-column label="市场" show-overflow-tooltip>
          <template #default="{ row }">{{ row.question_zh || row.question }}</template>
        </el-table-column>
        <el-table-column label="YES价格" width="100">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="买/卖" width="110">
          <template #default="{ row }">${{ (row.best_ask || row.yes_price).toFixed(3) }} / ${{ (row.best_bid || row.yes_price).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="到期" width="120">
          <template #default="{ row }">{{ row.end_date_bj || selected?.end_date_bj || '-' }}</template>
        </el-table-column>
	      </el-table>
	    </el-dialog>

	    <el-dialog v-model="adviceVisible" title="AI 风控提示" width="720">
	      <div v-if="advice">
	        <el-alert :type="adviceAlertType(advice)" show-icon :closable="false" style="margin-bottom:12px">
	          <template #title>
	            {{ advice.summary }} ｜ 风险 {{ advice.risk_label }} ｜ {{ advice.suggested_action }}
	          </template>
	        </el-alert>
	        <el-descriptions :column="2" border size="small" style="margin-bottom:12px">
	          <el-descriptions-item label="机会">{{ advice.title }}</el-descriptions-item>
	          <el-descriptions-item label="金额">${{ Number(advice.amount || 0).toFixed(2) }}</el-descriptions-item>
	          <el-descriptions-item label="结论">
	            <el-tag :type="advice.allowed ? (advice.risk_level === 'low' ? 'success' : 'warning') : 'danger'" size="small">{{ advice.verdict }}</el-tag>
	          </el-descriptions-item>
	          <el-descriptions-item label="引擎">{{ advice.engine }}</el-descriptions-item>
	        </el-descriptions>
	        <div v-if="advice.blockers?.length" class="advice-section">
	          <div class="advice-title danger">阻断项</div>
	          <ul><li v-for="b in advice.blockers" :key="b">{{ b }}</li></ul>
	        </div>
	        <div v-if="advice.warnings?.length" class="advice-section">
	          <div class="advice-title warn">风险提示</div>
	          <ul><li v-for="w in advice.warnings" :key="w">{{ w }}</li></ul>
	        </div>
	        <div v-if="advice.tips?.length" class="advice-section">
	          <div class="advice-title">操作提示</div>
	          <ul><li v-for="t in advice.tips" :key="t">{{ t }}</li></ul>
	        </div>
	        <el-table :data="advice.checks || []" size="small" style="margin-top:10px">
	          <el-table-column prop="label" label="检查项" width="120" />
	          <el-table-column label="状态" width="90">
	            <template #default="{ row }">
	              <el-tag :type="row.status === 'pass' ? 'success' : row.status === 'warn' ? 'warning' : 'danger'" size="small">{{ row.status }}</el-tag>
	            </template>
	          </el-table-column>
	          <el-table-column prop="detail" label="详情" show-overflow-tooltip />
	        </el-table>
	      </div>
	    </el-dialog>

	    <el-dialog v-model="intelAiVisible" title="真实 AI 复核" width="760">
	      <div v-if="intelAiTitle" style="font-weight:600;margin-bottom:8px">{{ intelAiTitle }}</div>
	      <el-alert type="info" show-icon :closable="false" style="margin-bottom:12px" title="模型复核" description="这里会真实调用你在系统里配置的 AI 模型；若结论为禁止/不建议下单，买入流程会被阻断。" />
	      <pre class="ai-review">{{ intelAiResult || '等待 AI 返回...' }}</pre>
	    </el-dialog>
	  </div>
	</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { arbitrageApi, aiApi, opportunityApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeTab = ref('basket')
const loading = ref(false)
const threshold = ref(0.03)
const results = ref<any[]>([])
const showDetail = ref(false)
const showHelp = ref(false)
const selected = ref<any>(null)
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predicting = ref(false)
const prediction = ref('')
const precheckBudget = ref(100)
const precheckLoading = ref(false)
const basketCheck = ref<any>(null)
const basketCheckBudget = ref<number | null>(null)
const basketBuyLoading = ref(false)
const minProfitPct = ref(0.2)
const quickAmount = ref(10)
const makerAmount = ref(10)
const actionLoading = ref('')
const cancelAllLoading = ref(false)
const adviceVisible = ref(false)
const advice = ref<any>(null)
const adviceLoading = ref(false)
const intelAiVisible = ref(false)
const intelAiLoading = ref('')
const intelAiTitle = ref('')
const intelAiResult = ref('')

const slippageLoading = ref(false)
const slippageBatchLoading = ref(false)
const slippageParams = ref({ amount: 25, max_slippage_pct: 2, min_volume_24h: 5000, max_candidates: 120 })
const slippageResults = ref<any[]>([])
const slippageSelected = ref<any[]>([])

const crossLoading = ref(false)
const crossParams = ref({ min_spread: 0.08, max_candidates: 300 })
const crossResults = ref<any[]>([])

const rewardsLoading = ref(false)
const rewardsResults = ref<any[]>([])

const resolutionLoading = ref(false)
const resolutionParams = ref({ hours: 12, min_volume_24h: 1000 })
const resolutionResults = ref<any[]>([])

const hedgeLoading = ref(false)
const hedgeCloseLoading = ref(false)
const hedgeResults = ref<any[]>([])
const hedgeSelected = ref<any[]>([])

const btcLoading = ref(false)
const btcNotifyLoading = ref(false)
const btcParams = ref({ min_edge: 0.04 })
const btcResults = ref<any[]>([])

const newsLoading = ref(false)
const newsParams = ref({ category: 'politics', lookback_hours: 48, max_candidates: 24 })
const newsResults = ref<any[]>([])

const scheduleLoading = ref(false)
const scheduleParams = ref({ days_ahead: 7, max_candidates: 120, include_unsupported: true })
const scheduleResults = ref<any[]>([])

const smartLoading = ref(false)
const smartParams = ref({ lookback_hours: 72, limit: 2500, min_notional: 10, top_wallets: 30 })
const smartReport = ref<any>(null)
const smartWallets = ref<any[]>([])
const smartAutoSeconds = ref(0)
let smartAutoTimer: ReturnType<typeof setInterval> | null = null

async function scan() {
  loading.value = true
  try {
    const { data } = await arbitrageApi.scan(threshold.value, precheckBudget.value)
    results.value = data || []
    if (results.value.length === 0) ElMessage.info('未发现套利机会')
  } catch {} finally { loading.value = false }
}

function selectRow(row: any) {
  selected.value = row
  basketCheck.value = null
  basketCheckBudget.value = null
  prediction.value = ''
}

function expandDetail(row: any) {
  selected.value = row
  basketCheck.value = null
  basketCheckBudget.value = null
  showDetail.value = true
  prediction.value = ''
}

async function precheckRow(row: any) {
  selected.value = row
  await precheckSelectedBasket()
  showDetail.value = true
}

function normalizeBudget(value: any) {
  const budget = Number(value)
  if (!Number.isFinite(budget) || budget < 5) {
    throw new Error('篮子预算至少 5 USDC')
  }
  if (budget > 10000) {
    throw new Error('篮子预算不能超过 10000 USDC')
  }
  return Math.round(budget * 100) / 100
}

async function fetchBasketPrecheck(row: any, budget: number) {
  const { data } = await opportunityApi.basketPrecheck({ event_slug: row.event_slug, budget })
  basketCheck.value = data
  basketCheckBudget.value = Number(data.budget_usdc || budget)
  return data
}

async function askBasketBudget() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入本次整篮买入预算。这里不是单腿金额，系统会用这笔总预算重新预检并按同等份额买入所有 YES。',
      '设置篮子预算',
      {
        inputValue: String(precheckBudget.value),
        inputType: 'number',
        inputPattern: /^(?:(?:[5-9]|[1-9]\d{1,3})(?:\.\d{1,2})?|10000(?:\.0{1,2})?)$/,
        inputErrorMessage: '请输入 5 - 10000 之间的 USDC 金额',
        confirmButtonText: '按此预算预检',
        cancelButtonText: '取消',
      }
    )
    const budget = normalizeBudget(value)
    precheckBudget.value = budget
    return budget
  } catch {
    return null
  }
}

async function precheckSelectedBasket() {
  if (!selected.value?.event_slug) return
  precheckLoading.value = true
  try {
    const budget = normalizeBudget(precheckBudget.value)
    precheckBudget.value = budget
    await fetchBasketPrecheck(selected.value, budget)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '预检失败')
  } finally { precheckLoading.value = false }
}

function actionKey(row: any, action: string) {
  return `${action}:${row?.event_slug || row?.market_slug || row?.slug || row?.token_id || row?.asset || row?.wallet || row?.topic || row?.title || ''}`
}

function basketStatusLabel(row: any) {
  if (!row?.integrity?.ok) return '漏项风险'
  if (row.executable) return '可买入'
  if (row.can_shadow) return '可补腿'
  return '观察'
}

function basketStatusType(row: any) {
  if (!row?.integrity?.ok) return 'danger'
  if (row.executable) return 'success'
  if (row.can_shadow) return 'warning'
  return 'info'
}

function buyPayload(row: any, amount: number, extra: any = {}) {
  return {
    token_id: extra.token_id || row?.token_id || row?.token_ids?.[0],
    amount,
    tick_size: row?.tick_size || extra.tick_size || '0.01',
    neg_risk: Boolean(row?.neg_risk ?? extra.neg_risk ?? false),
    market_slug: row?.slug || extra.market_slug || '',
    condition_id: row?.condition_id || extra.condition_id || '',
    order_type: extra.order_type || 'FOK',
    size: extra.size || 0,
    limit_price: extra.limit_price || 0,
  }
}

function adviceAlertType(data: any) {
  if (!data?.allowed) return 'error'
  if (data.risk_level === 'low') return 'success'
  if (data.risk_level === 'medium') return 'warning'
  if (data.risk_level === 'high') return 'warning'
  return 'error'
}

function adviceKindFromAction(action: string) {
  if (action.startsWith('res-')) return 'resolution'
  if (action.startsWith('news-')) return 'news'
  if (action.startsWith('schedule-')) return 'schedule'
  if (action.startsWith('smart')) return 'smart_money'
  if (action === 'slippage') return 'slippage'
  if (action === 'btc') return 'btc'
  if (action === 'maker') return 'rewards'
  if (action.startsWith('cross')) return 'cross'
  return 'unknown'
}

async function fetchAdvice(row: any, kind: string, amount: number, context: any = {}) {
  const { data } = await opportunityApi.advice({ kind, item: row, amount, context })
  return data
}

async function showAdvice(row: any, kind: string, amount: any, context: any = {}) {
  adviceLoading.value = true
  try {
    advice.value = await fetchAdvice(row, kind, Number(amount || 0), context)
    adviceVisible.value = true
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 风控失败')
  } finally {
    adviceLoading.value = false
  }
}

async function confirmWithAdvice(row: any, kind: string, amount: number, context: any = {}, title = '确认执行') {
  const data = await fetchAdvice(row, kind, amount, context)
  advice.value = data
  if (!data.allowed) {
    adviceVisible.value = true
    await ElMessageBox.alert(data.confirm_text, 'AI 风控阻断', { type: 'error', confirmButtonText: '知道了' })
    return false
  }
  await ElMessageBox.confirm(data.confirm_text, title, {
    type: data.risk_level === 'low' ? 'info' : 'warning',
    confirmButtonText: '确认执行',
    cancelButtonText: '取消',
  })
  return true
}

function intelPrompt(kind: string, row: any, side = '') {
  const common = {
    kind,
    side,
    amount: quickAmount.value,
    title: row.title_zh || row.question_zh || row.title || row.question,
    yes_price: row.yes_price,
    no_price: row.no_price,
    end_date_bj: row.end_date_bj,
    volume_24h: row.volume_24h,
  }
  const payload = kind === 'news'
    ? {
        ...common,
        latest_headline: row.latest_headline_zh || row.latest_headline,
        news_count: row.news_count,
        signal_score: row.signal_score,
        headlines: (row.headlines || []).slice(0, 5).map((h: any) => ({
          title: h.title_zh || h.title,
          source: h.source,
          published_at_bj: h.published_at_bj,
        })),
      }
    : {
        ...common,
        league: row.league || row.league_guess,
        game: row.game || row.teams,
        game_time_bj: row.game_time_bj,
        game_status: row.game_status,
        espn_supported: row.espn_supported,
        action_note: row.action,
        markets: (row.markets || []).slice(0, 4).map((m: any) => ({
          question: m.question_zh || m.question,
          yes_price: m.yes_price,
          no_price: m.no_price,
          end_date_bj: m.end_date_bj,
        })),
      }

  return `请对下面这个 Polymarket ${kind === 'news' ? '新闻催化' : '赛程'}机会做下单前复核。

要求：
1. 第一行必须写：结论：通过 / 谨慎 / 禁止
2. 判断新闻或赛程是否和市场结算规则直接相关。
3. 给出 YES/NO 概率估计、当前价格是否有边际、是否建议买入 ${side || 'YES/NO'}。
4. 如果信息不足、标题不匹配、赛程疑似不覆盖、比赛可能已结束，请明确写“禁止”或“不建议下单”。
5. 用简体中文，短而直接。

数据：
${JSON.stringify(payload, null, 2)}`
}

function aiReviewBlocks(text: string) {
  return /结论[:：]\s*禁止|禁止下单|不要下单|不建议下单|不建议买入|不建议买/.test(text || '')
}

async function fetchIntelAiReview(row: any, kind: 'news' | 'schedule', side = '') {
  if (!aiConfigId.value) {
    ElMessage.warning('请先选择 AI 模型')
    return ''
  }
  const key = actionKey(row, `${kind}-ai`)
  intelAiLoading.value = key
  intelAiTitle.value = row.title_zh || row.question_zh || row.title || row.question || 'AI 复核'
  intelAiResult.value = ''
  try {
    const { data } = await aiApi.analyze({
      ai_config_id: aiConfigId.value,
      system_prompt: '你是 Polymarket 交易前风控员，任务是保守把关，资金安全第一。必须用简体中文回答。',
      prompt: intelPrompt(kind, row, side),
    })
    intelAiResult.value = data.result || ''
    intelAiVisible.value = true
    return intelAiResult.value
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 复核失败')
    return ''
  } finally {
    intelAiLoading.value = ''
  }
}

async function runIntelAiReview(row: any, kind: 'news' | 'schedule') {
  await fetchIntelAiReview(row, kind)
}

async function confirmIntelAi(row: any, kind: 'news' | 'schedule', side: string) {
  const result = await fetchIntelAiReview(row, kind, side)
  if (!result) return false
  if (aiReviewBlocks(result)) {
    await ElMessageBox.alert(result, 'AI 复核阻断', { type: 'error', confirmButtonText: '知道了' })
    return false
  }
  await ElMessageBox.confirm(`AI 复核未阻断。\n\n${result.slice(0, 700)}\n\n仍要继续提交 ${side} FOK 买入吗？`, '确认 AI 复核结果', {
    type: 'warning',
    confirmButtonText: '继续提交',
    cancelButtonText: '取消',
  })
  return true
}

async function buyBasket(row: any, askAmount = false) {
  if (!row?.event_slug) return
  if (!row.integrity?.ok) {
    ElMessage.error(row.integrity?.note || '池子完整性未通过，禁止一键买入')
    return
  }
  if (row.direction !== 'BUY_YES' || !row.executable) {
    ElMessage.warning('这个篮子不是可直接买入的 BUY_YES 机会')
    return
  }
  selected.value = row
  let budget: number | null = null
  try {
    budget = askAmount ? await askBasketBudget() : normalizeBudget(precheckBudget.value)
  } catch (err: any) {
    ElMessage.error(err?.message || '篮子预算无效')
    return
  }
  if (budget === null) return
  precheckBudget.value = budget
  const key = actionKey(row, 'basket')
  actionLoading.value = key
  basketBuyLoading.value = true
  try {
    const check = await fetchBasketPrecheck(row, budget)
    if (!check.fillable) {
      ElMessage.warning(check.note || '当前盘口预检不可执行')
      return
    }
    const merged = { ...row, ...check, event_slug: row.event_slug, direction: row.direction || 'BUY_YES', executable: check.fillable }
    const okToSubmit = await confirmWithAdvice(merged, 'basket', budget, { min_profit_pct: minProfitPct.value }, '确认一键买入篮子')
    if (!okToSubmit) return
    const { data } = await opportunityApi.basketBuy({
      event_slug: row.event_slug,
      budget,
      min_profit_pct: minProfitPct.value,
    })
    if (data.precheck) {
      basketCheck.value = data.precheck
      basketCheckBudget.value = Number(data.precheck.budget_usdc || budget)
    }
    const ok = data.orders?.length || 0
    const fail = data.failed?.length || 0
    ElMessage.success(`篮子订单已提交：预算 $${budget}，成功 ${ok} 条，失败 ${fail} 条`)
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || err?.message || '篮子买入失败')
    }
  } finally {
    basketBuyLoading.value = false
    actionLoading.value = ''
  }
}

async function quickBuy(row: any, amount: number, keyAction: string, extra: any = {}) {
  const payload = buyPayload(row, amount, extra)
  if (!payload.token_id) {
    ElMessage.warning('缺少 token_id，无法下单')
    return
  }
  try {
    const kind = extra.advice_kind || adviceKindFromAction(keyAction)
    const okToSubmit = await confirmWithAdvice(row, kind, amount, extra.advice_context || {}, '确认快捷买入')
    if (!okToSubmit) return
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 风控失败')
    return
  }
  const key = actionKey(row, keyAction)
  actionLoading.value = key
  try {
    const { data } = await opportunityApi.quickBuy(payload)
    ElMessage.success(`买入已提交: ${data.size?.toFixed?.(2) || data.size} 份 @ $${data.price}`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '买入失败')
  } finally {
    actionLoading.value = ''
  }
}

function buySlippage(row: any) {
  return quickBuy(row, slippageParams.value.amount, 'slippage', {
    size: row.depth?.shares || 0,
    limit_price: row.depth?.worst_price || 0,
    order_type: 'FOK',
    advice_kind: 'slippage',
    advice_context: { max_slippage_pct: slippageParams.value.max_slippage_pct },
  })
}

function onSlippageSelection(rows: any[]) {
  slippageSelected.value = rows
}

async function buySelectedSlippage() {
  if (slippageSelected.value.length === 0) {
    ElMessage.warning('请先勾选要批量买入的盘口')
    return
  }
  slippageBatchLoading.value = true
  try {
    const total = slippageParams.value.amount * slippageSelected.value.length
    await ElMessageBox.confirm(
      `将对 ${slippageSelected.value.length} 个盘口各投入约 $${slippageParams.value.amount}，合计约 $${total}。提交前后端会重新检查滑点不超过 ${slippageParams.value.max_slippage_pct}%，任意一条不达标会取消整批。`,
      '确认批量买入低滑点盘口',
      { type: 'warning', confirmButtonText: '批量提交', cancelButtonText: '取消' }
    )
    const { data } = await opportunityApi.slippageBatchBuy({
      items: slippageSelected.value,
      amount: slippageParams.value.amount,
      max_slippage_pct: slippageParams.value.max_slippage_pct,
    })
    const ok = data.orders?.length || 0
    const fail = data.failed?.length || 0
    if (data.success) {
      ElMessage.success(`批量买入已提交：${ok} 条，预检成本 $${data.total_checked_cost}`)
    } else {
      ElMessage.warning(`批量买入未完全成功：成功 ${ok} 条，失败 ${fail} 条，请到订单页核对`)
    }
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || err?.message || '批量买入失败')
    }
  } finally {
    slippageBatchLoading.value = false
  }
}

async function buyCrossHedge(row: any) {
  if (!row?.buy_candidate || !row?.sell_reference) {
    ElMessage.warning('缺少低价候选或高价参考，无法双边下单')
    return
  }
  const budget = Number(quickAmount.value)
  if (!Number.isFinite(budget) || budget < 1 || budget > 10000) {
    ElMessage.warning('双边预算请输入 1 - 10000 USDC')
    return
  }
  const depth = row.pair_depth || {}
  if (!depth.fillable) {
    ElMessage.warning(depth.reason || '当前同题价差没有足够可盈利双边深度')
    return
  }
  const key = actionKey(row, 'cross-smart')
  actionLoading.value = key
  try {
    const okToSubmit = await confirmWithAdvice(row, 'cross', budget, { min_profit_pct: minProfitPct.value }, '确认同题双边套利')
    if (!okToSubmit) return
    const { data } = await opportunityApi.crossHedgeBuy({
      buy_candidate: row.buy_candidate,
      sell_reference: row.sell_reference,
      amount: budget,
      min_profit_pct: minProfitPct.value,
    })
    const executed = data.depth || {}
    const ok = data.orders?.length || 0
    const fail = data.failed?.length || 0
    if (data.success) {
      ElMessage.success(`双边订单已提交：成本 $${executed.total_cost}，份额 ${executed.target_shares}，成功 ${ok} 腿`)
    } else {
      ElMessage.warning(`双边订单未完全成功：成功 ${ok} 腿，失败 ${fail} 腿；系统已尝试撤销残留订单，请到订单页核对`)
    }
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || err?.message || '同题双边套利失败')
    }
  } finally {
    actionLoading.value = ''
  }
}

async function buyCandidate(row: any) {
  try {
    await ElMessageBox.confirm('同题价差需要人工确认结算口径一致；这里仅买入低价候选，不会自动完成对冲。', '确认买入候选', {
      type: 'warning',
      confirmButtonText: '买入',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  return quickBuy(row, quickAmount.value, 'cross')
}

function buyOutcome(row: any, idx: number, label: string) {
  if (!row.can_buy) {
    ElMessage.warning(row.trade_disabled_reason || '该临近结算市场当前不可下单')
    return
  }
  return quickBuy(row, quickAmount.value, `res-${label.toLowerCase()}`, {
    token_id: row.token_ids?.[idx],
    advice_kind: 'resolution',
  })
}

function buyBtcAlert(row: any) {
  const market = row.market || {}
  const idx = row.action === '买DOWN' ? 1 : 0
  return quickBuy(row, quickAmount.value, 'btc', {
    token_id: market.token_ids?.[idx],
    market_slug: market.slug || '',
    condition_id: market.condition_id || '',
    tick_size: market.tick_size || '0.01',
    neg_risk: market.neg_risk || false,
    advice_kind: 'btc',
  })
}

async function buyNews(row: any, idx: number, label: string) {
  if (!await confirmIntelAi(row, 'news', label)) return
  return quickBuy(row, quickAmount.value, `news-${label.toLowerCase()}`, {
    token_id: row.token_ids?.[idx],
    market_slug: row.slug || '',
    condition_id: row.condition_id || '',
    tick_size: row.tick_size || '0.01',
    neg_risk: row.neg_risk || false,
    advice_kind: 'news',
  })
}

async function buySchedule(row: any, idx: number, label: string) {
  if (!row.can_buy) {
    ElMessage.warning(row.trade_disabled_reason || '该赛程市场当前不可下单')
    return
  }
  if (!await confirmIntelAi(row, 'schedule', label)) return
  return quickBuy(row, quickAmount.value, `schedule-${label.toLowerCase()}`, {
    token_id: row.token_ids?.[idx],
    market_slug: row.market_slug || row.slug || '',
    condition_id: row.condition_id || '',
    tick_size: row.tick_size || '0.01',
    neg_risk: row.neg_risk || false,
    advice_kind: 'schedule',
  })
}

async function followSmartMoney(row: any) {
  const trade = row.last_buy_trade
  if (!trade?.token_id) {
    ElMessage.warning('没有可跟买的最近 BUY token')
    return
  }
  return quickBuy(trade, quickAmount.value, 'smart-follow', {
    token_id: trade.token_id,
    market_slug: trade.market_slug || '',
    condition_id: trade.condition_id || '',
    tick_size: '0.01',
    advice_kind: 'smart_money',
    advice_context: { wallet: row.wallet },
  })
}

async function quoteMaker(row: any) {
  const key = actionKey(row, 'maker')
  actionLoading.value = key
  try {
    const okToSubmit = await confirmWithAdvice(row, 'rewards', makerAmount.value, {}, '确认奖励做市委托')
    if (!okToSubmit) return
    const { data } = await opportunityApi.makerQuote({
      market_slug: row.slug,
      amount_per_side: makerAmount.value,
      improve_ticks: 0,
    })
    ElMessage.success(`做市委托已提交：${data.orders?.length || 0} 条`)
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') ElMessage.error(err?.response?.data?.detail || err?.message || '做市委托失败')
  } finally {
    actionLoading.value = ''
  }
}

async function sellHolding(row: any) {
  if (!row.asset) {
    ElMessage.warning('缺少持仓 token，无法卖出')
    return
  }
  const key = actionKey(row, 'sell')
  actionLoading.value = key
  try {
    await ElMessageBox.confirm(`将按当前 best bid 卖出 ${row.size.toFixed(2)} 份 ${row.outcome || ''}。`, '确认卖出持仓', {
      type: 'warning',
      confirmButtonText: '卖出',
      cancelButtonText: '取消',
    })
    const { data } = await opportunityApi.quickSell({
      token_id: row.asset,
      size: row.size,
      tick_size: row.tick_size || '0.01',
      neg_risk: row.neg_risk || false,
      market_slug: row.slug || '',
      condition_id: row.condition_id || '',
    })
    ElMessage.success(`卖出已提交: ${data.size?.toFixed?.(2) || data.size} 份 @ $${data.price}`)
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') ElMessage.error(err?.response?.data?.detail || err?.message || '卖出失败')
  } finally {
    actionLoading.value = ''
  }
}

function onHedgeSelection(rows: any[]) {
  hedgeSelected.value = rows
}

async function closeSelectedHedges() {
  if (hedgeSelected.value.length === 0) {
    ElMessage.warning('请先勾选要平仓的持仓')
    return
  }
  hedgeCloseLoading.value = true
  try {
    const value = hedgeSelected.value.reduce((sum, row) => sum + Number(row.current_value || 0), 0)
    await ElMessageBox.confirm(
      `将对 ${hedgeSelected.value.length} 个持仓按当前买盘深度预检并 FOK 平仓，当前市值约 $${value.toFixed(2)}。任意一条买盘深度不足会取消整批。`,
      '确认批量平仓',
      { type: 'warning', confirmButtonText: '批量平仓', cancelButtonText: '取消' }
    )
    const { data } = await opportunityApi.hedgeClose({ items: hedgeSelected.value, fraction: 1 })
    const ok = data.orders?.length || 0
    const fail = data.failed?.length || 0
    if (data.success) {
      ElMessage.success(`批量平仓已提交：${ok} 条 FOK 卖单`)
      await loadHedges()
    } else {
      ElMessage.warning(`批量平仓未完全成功：成功 ${ok} 条，失败 ${fail} 条，请到订单页核对`)
    }
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || err?.message || '批量平仓失败')
    }
  } finally {
    hedgeCloseLoading.value = false
  }
}

async function cancelAllOpenOrders() {
  cancelAllLoading.value = true
  try {
    await ElMessageBox.confirm('将撤销当前账号在 Polymarket 的所有未成交挂单。这个按钮适合做市失控或行情突变时使用。', '确认紧急全撤', {
      type: 'warning',
      confirmButtonText: '全部撤单',
      cancelButtonText: '取消',
    })
    await opportunityApi.cancelAll()
    ElMessage.success('已提交全部撤单')
  } catch (err: any) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || err?.message || '紧急撤单失败')
    }
  } finally {
    cancelAllLoading.value = false
  }
}

async function runPredict() {
  if (!selected.value || !aiConfigId.value) return
  predicting.value = true
  prediction.value = ''
  try {
    const { data } = await aiApi.analyzeArbitrage({ ai_config_id: aiConfigId.value, event_slug: selected.value.event_slug, yes_sum: selected.value.yes_sum })
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

async function loadSlippage() {
  slippageLoading.value = true
  try {
    const { data } = await opportunityApi.slippage(slippageParams.value)
    slippageResults.value = data || []
    slippageSelected.value = []
  } finally { slippageLoading.value = false }
}

async function loadCross() {
  crossLoading.value = true
  try {
    const { data } = await opportunityApi.crossEvent({ ...crossParams.value, budget: quickAmount.value })
    crossResults.value = data || []
  } finally { crossLoading.value = false }
}

async function loadRewards() {
  rewardsLoading.value = true
  try {
    const { data } = await opportunityApi.rewards()
    rewardsResults.value = data || []
  } finally { rewardsLoading.value = false }
}

async function loadResolution() {
  resolutionLoading.value = true
  try {
    const { data } = await opportunityApi.resolutionWatch(resolutionParams.value)
    resolutionResults.value = data || []
  } finally { resolutionLoading.value = false }
}

async function loadHedges() {
  hedgeLoading.value = true
  try {
    const { data } = await opportunityApi.hedges()
    hedgeResults.value = data || []
    hedgeSelected.value = []
  } finally { hedgeLoading.value = false }
}

async function loadBtcAlerts() {
  btcLoading.value = true
  try {
    const { data } = await opportunityApi.btcAlerts(btcParams.value)
    btcResults.value = data || []
    if (btcResults.value.length === 0) ElMessage.info('暂无满足条件的 BTC 提醒')
  } finally { btcLoading.value = false }
}

async function notifyBtc() {
  btcNotifyLoading.value = true
  try {
    const { data } = await opportunityApi.notifyBtcAlerts(btcParams.value)
    ElMessage.success(data.message || '已推送')
  } finally { btcNotifyLoading.value = false }
}

async function loadNews() {
  newsLoading.value = true
  try {
    const { data } = await opportunityApi.newsCatalysts(newsParams.value)
    newsResults.value = data || []
    if (newsResults.value.length === 0) ElMessage.info('暂无新闻催化信号')
  } finally { newsLoading.value = false }
}

async function loadSchedule() {
  scheduleLoading.value = true
  try {
    const { data } = await opportunityApi.sportsSchedule(scheduleParams.value)
    scheduleResults.value = data || []
    if (scheduleResults.value.length === 0) ElMessage.info('暂无赛程匹配结果')
  } finally { scheduleLoading.value = false }
}

async function loadSmartMoney() {
  if (smartLoading.value) return
  smartLoading.value = true
  try {
    const { data } = await opportunityApi.smartMoney(smartParams.value)
    smartReport.value = data
    smartWallets.value = data?.wallets || []
    if (smartWallets.value.length === 0) ElMessage.info('暂无满足条件的聪明钱钱包')
  } finally { smartLoading.value = false }
}

function resetSmartAutoRefresh() {
  if (smartAutoTimer) {
    clearInterval(smartAutoTimer)
    smartAutoTimer = null
  }
  const seconds = Number(smartAutoSeconds.value || 0)
  if (activeTab.value === 'smart' && seconds >= 5) {
    smartAutoTimer = setInterval(() => {
      loadSmartMoney()
    }, seconds * 1000)
  }
}

function riskTagType(level: string) {
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  if (level === 'success') return 'success'
  return 'info'
}

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

watch(precheckBudget, () => {
  basketCheck.value = null
  basketCheckBudget.value = null
})

watch([smartAutoSeconds, activeTab], resetSmartAutoRefresh)

onMounted(() => {
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})

onUnmounted(() => {
  if (smartAutoTimer) clearInterval(smartAutoTimer)
})
</script>

<style scoped>
.advice-section {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.6;
}

.advice-section ul {
  margin: 4px 0 0;
  padding-left: 18px;
}

.advice-title {
  font-weight: 600;
  color: #303133;
}

.advice-title.warn {
  color: #b88230;
}

.advice-title.danger {
  color: #c45656;
}

.ai-review {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  background: #f7f8fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  max-height: 520px;
  overflow: auto;
}
</style>
