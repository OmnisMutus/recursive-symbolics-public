//go:build windows

package apis

func surrogateTagForTest(tag uint32) bool { return isNameSurrogate(tag) }
