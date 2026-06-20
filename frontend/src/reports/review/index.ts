import { mount, unmount } from "svelte";

import { getUrlPath } from "../../helpers.ts";
import { _ } from "../../i18n.ts";
import { type Result, err, ok } from "../../lib/result.ts";
import type { FrontendRoute, RenderedReport } from "../route.ts";
import { ReportLoadError } from "../ReportLoadError.svelte";
import ReviewDetail from "./ReviewDetail.svelte";
import ReviewList from "./ReviewList.svelte";

type ReviewView =
  | { kind: "list" }
  | { kind: "detail"; id: string };

class NotAReviewUrlError extends Error {
  constructor(pathname: string) {
    super(`Path '${pathname}' is not a path for the review report.`);
  }
}

export function get_review_view_from_url(
  url: URL,
): Result<ReviewView, unknown> {
  const pathResult = getUrlPath(url);
  if (pathResult.is_err) {
    return err(pathResult.error);
  }
  const relative_path = pathResult.value;
  const parts = relative_path.split("/");
  const [base, id_encoded] = parts;

  if (base !== "review") {
    return err(new NotAReviewUrlError(relative_path));
  }

  if (id_encoded == null || id_encoded === "") {
    return ok({ kind: "list" });
  }

  const id = decodeURIComponent(id_encoded);
  return ok({ kind: "detail", id });
}

type ReviewWrapperProps = { view: ReviewView };

class ReviewRouterComponent {
  #target: HTMLElement;
  #current:
    | { component: unknown; destroy: () => void; kind: string; id?: string }
    | undefined;

  constructor(options: { target: HTMLElement; props: ReviewWrapperProps }) {
    this.#target = options.target;
    this.#render(options.props.view);
  }

  $set(props: ReviewWrapperProps) {
    const view = props.view;
    const kind = view.kind;
    const id = view.kind === "detail" ? view.id : undefined;

    if (
      this.#current &&
      this.#current.kind === kind &&
      (kind === "list" || this.#current.id === id)
    ) {
      return;
    }

    this.#current?.destroy();
    this.#render(view);
  }

  #render(view: ReviewView) {
    if (view.kind === "list") {
      const component = mount(ReviewList, { target: this.#target });
      this.#current = {
        component,
        destroy: () => void unmount(component),
        kind: "list",
      };
    } else {
      const component = mount(ReviewDetail, {
        target: this.#target,
        props: { id: view.id },
      });
      this.#current = {
        component,
        destroy: () => void unmount(component),
        kind: "detail",
        id: view.id,
      };
    }
  }

  $destroy() {
    this.#current?.destroy();
    this.#current = undefined;
  }
}

export class ReviewRoute implements FrontendRoute {
  readonly report = "review";

  async render(
    target: HTMLElement,
    url: URL,
    previous?: RenderedReport,
    before_render?: () => void,
  ): Promise<RenderedReport> {
    try {
      const viewResult = get_review_view_from_url(url);
      const view = viewResult.unwrap();
      const props = { view };

      previous?.destroy();
      before_render?.();

      const component = mount(ReviewRouterComponent as never, {
        target,
        props,
      });

      const title = this.get_title(url);
      return new RenderedReport(this, url, title, () => {
        void unmount(component);
      });
    } catch (error: unknown) {
      previous?.destroy();
      before_render?.();
      if (error instanceof Error) {
        const instance = mount(ReportLoadError, {
          target,
          props: { title: url.pathname, error },
        });
        return new RenderedReport(this, url, _("Error"), () => {
          void unmount(instance);
        });
      }
      throw error;
    }
  }

  get_title(url: URL): string {
    try {
      const viewResult = get_review_view_from_url(url);
      if (viewResult.is_ok) {
        const view = viewResult.value;
        if (view.kind === "detail") {
          return _("Review Desk - Detail");
        }
      }
    } catch {
      // fall through
    }
    return _("Review Desk");
  }
}

export const review_route = new ReviewRoute();
