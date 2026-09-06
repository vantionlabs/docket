import { redirect } from "next/navigation";

/**
 * The queue is the product, so it is what signing in lands on. Chat moved
 * to /chat: still useful for asking the policy corpus questions, but not
 * what a reviewer opens this app to do.
 */
export default function Home() {
  redirect("/queue");
}
