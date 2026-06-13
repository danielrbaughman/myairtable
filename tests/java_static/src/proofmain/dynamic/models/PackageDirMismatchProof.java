// Package-vs-directory compile proof (java-plan-v2 §2.3.5): this file declares
// `package myairtable` while living under src/proofmain/dynamic/models/ — the
// exact layout the generator emits (output/dynamic/models/*.java, flat package).
// Gradle passes explicit source lists to javac (no sourcepath resolution), so
// the mismatch must compile. TestPojoModel references the constant to prove it.

package myairtable;

public final class PackageDirMismatchProof {
  public static final String PROOF = "package-dir-mismatch-compiles";

  private PackageDirMismatchProof() {}
}
