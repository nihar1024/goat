import { redirect } from "next/navigation";

export default async function WhiteLabelLanding() {
  return redirect("/settings/organization/white-label/domains");
}
