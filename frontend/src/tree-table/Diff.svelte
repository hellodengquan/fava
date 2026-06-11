<script lang="ts">
  import { ctx } from "../stores/format.ts";

  type BudgetStatus = "ok" | "near" | "over";

  interface Props {
    diff: number;
    num: number;
    currency: string;
    status?: BudgetStatus;
    ratio?: number;
    show_progress?: boolean;
  }

  let { diff, num, currency, status, ratio, show_progress = true }: Props = $props();
  let positive = $derived(diff > 0);
  let computed_status = $derived<BudgetStatus>(() => {
    if (status) return status;
    if (num <= 0) return "ok";
    const used_ratio = 1 - diff / num;
    if (used_ratio >= 1.0) return "over";
    if (used_ratio >= 0.8) return "near";
    return "ok";
  });
  let display_ratio = $derived(() => {
    if (ratio != null) return ratio;
    if (num <= 0) return 0;
    return 1 - diff / num;
  });
  let clamped_ratio = $derived(Math.min(Math.max(display_ratio, 0), 1.5));
</script>

{#if show_progress}
  <div class="progress-bar" class:near={computed_status === "near"} class:over={computed_status === "over"}>
    <div class="progress-fill" style={`width: ${Math.min(clamped_ratio * 100, 150)}%`} />
  </div>
{/if}
<br />
<span
  class:positive
  class:near={computed_status === "near"}
  class:over={computed_status === "over"}
  title={$ctx.amount(num, currency)}
>
  ({positive ? "+" : "-"}{$ctx.num(Math.abs(diff), currency)})
  {#if computed_status === "over"}
    <span class="badge over">超支</span>
  {:else if computed_status === "near"}
    <span class="badge near">接近</span>
  {/if}
</span>

<style>
  span {
    margin-right: 3px;
    font-size: 0.9em;
    color: var(--diff-negative);
    white-space: nowrap;
  }

  .positive {
    color: var(--diff-positive);
  }

  .near {
    color: #f0ad4e;
    font-weight: 500;
  }

  .over {
    color: #d9534f;
    font-weight: 600;
  }

  .badge {
    display: inline-block;
    margin-left: 4px;
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 0.75em;
    font-weight: 600;
    line-height: 1.4;
  }

  .badge.near {
    background-color: #fcf8e3;
    color: #8a6d3b;
    border: 1px solid #faebcc;
  }

  .badge.over {
    background-color: #f2dede;
    color: #a94442;
    border: 1px solid #ebccd1;
  }

  .progress-bar {
    display: block;
    width: 60px;
    height: 4px;
    background-color: #e9ecef;
    border-radius: 2px;
    overflow: hidden;
    margin: 2px 0;
  }

  .progress-fill {
    height: 100%;
    background-color: var(--diff-positive);
    border-radius: 2px;
    transition: width 0.2s ease;
  }

  .progress-bar.near .progress-fill {
    background-color: #f0ad4e;
  }

  .progress-bar.over .progress-fill {
    background-color: #d9534f;
  }
</style>
