//go:build !windows

package apis

// Off Windows there are no reparse tags; the rule is the same bit test, kept here so the table runs.
func surrogateTagForTest(tag uint32) bool { return tag&0x20000000 != 0 }
